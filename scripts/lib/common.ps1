#Requires -Version 5.1
<#
    common.ps1 — AI Learning Memory OS DevOps 共享函数库
    Owner: devops-dev ｜ 范围: scripts/**（DEVOPS-01..06）

    由各入口脚本 dot-source 引入，例如（脚本位于 scripts/ 下时）：
        . (Join-Path $PSScriptRoot 'lib/common.ps1')

    兼容性：仅使用 Windows PowerShell 5.1 语法。
        - 不使用 && / || / ?? / ?. / 三元运算符 / $IsWindows（均为 PowerShell 7+ 特性）
        - 不使用 class，全部用函数
        - 不使用 $Host / $args / $input / $error 等自动变量名

    重要安全约定：
        - 密钥只从 .env / 进程环境变量读取，绝不打印值、绝不写入日志、绝不入库入 Git。
        - 缺失必需配置或仍是占位符时：启动类脚本必须 throw（明确报错），不得静默降级为 Mock/假数据。
        - 本文件及所有脚本均为「静态交付」；本次开发未安装依赖、未联网、未启动服务、
          未连接数据库、未注册系统任务、未调用外部 API。
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# $LASTEXITCODE 是自动变量，首次调用外部命令前并不存在；StrictMode 下先初始化，避免读取未定义变量报错。
$global:LASTEXITCODE = 0

# common.ps1 位于 <repo>/scripts/lib/，根目录为 ../..
$script:RepoRoot = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path

# 启动后端所必需的环境变量（缺失或占位符一律拒绝启动）
$script:RequiredEnvKeys = @('DATABASE_URL', 'SECRET_KEY')

# 占位符/未填写特征（大小写不敏感）；命中即视为「未配置」
$script:PlaceholderPatterns = @(
    'REPLACE_ME', 'CHANGEME', 'YOUR_', 'USER:PASSWORD',
    '@HOST:', '/DBNAME', 'PASTE_', '<YOUR', 'EXAMPLE', 'TODO'
)

# Transcript 状态（供 Start-ScriptLog / Stop-ScriptLog 使用）
$script:TranscriptActive = $false

# ---------------------------------------------------------------- 路径

function Get-RepoRoot    { return $script:RepoRoot }
function Get-BackendDir  { return (Join-Path $script:RepoRoot 'backend') }
function Get-FrontendDir { return (Join-Path $script:RepoRoot 'frontend') }
function Get-EnvFilePath {
    $projectEnv = Join-Path $script:RepoRoot '.env'
    if (Test-Path -LiteralPath $projectEnv) { return $projectEnv }
    return (Join-Path (Get-BackendDir) '.env')
}

function Get-VenvPython {
    # venv 在 Windows 为 Scripts/python.exe，在 Linux 为 bin/python（FR-12 迁移时同一脚本可用）
    $win = Join-Path (Join-Path $script:RepoRoot '.venv') 'Scripts/python.exe'
    $nix = Join-Path (Join-Path $script:RepoRoot '.venv') 'bin/python'
    if (Test-Path -LiteralPath $win) { return $win }
    if (Test-Path -LiteralPath $nix) { return $nix }
    return $null
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Info ("已创建目录：" + $Path)
    }
}

# ---------------------------------------------------------------- 日志

function Write-Step {
    param([string]$Message)
    Write-Host ("[STEP ] " + (Get-Date -Format 'HH:mm:ss') + " " + $Message) -ForegroundColor Cyan
}
function Write-Info {
    param([string]$Message)
    Write-Host ("[INFO ] " + (Get-Date -Format 'HH:mm:ss') + " " + $Message)
}
function Write-Warn {
    param([string]$Message)
    Write-Host ("[WARN ] " + (Get-Date -Format 'HH:mm:ss') + " " + $Message) -ForegroundColor Yellow
}
function Write-Err {
    param([string]$Message)
    Write-Host ("[ERROR] " + (Get-Date -Format 'HH:mm:ss') + " " + $Message) -ForegroundColor Red
}

function Start-ScriptLog {
    param([Parameter(Mandatory = $true)][string]$Name)
    $dir = Join-Path (Get-RepoRoot) 'logs'
    Ensure-Directory -Path $dir
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $dir ($Name + '-' + $stamp + '.log')
    try {
        Start-Transcript -Path $path -Force -ErrorAction Stop | Out-Null
        $script:TranscriptActive = $true
        Write-Info ("日志输出：" + $path)
    }
    catch {
        Write-Warn ("无法启动 Transcript（" + $_.Exception.Message + "），仅输出到控制台。")
        $script:TranscriptActive = $false
    }
}

function Stop-ScriptLog {
    if ($script:TranscriptActive) {
        try { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null } catch { }
        $script:TranscriptActive = $false
    }
}

# ---------------------------------------------------------------- .env 与配置校验

function Import-DotEnv {
    <#
        解析 .env（KEY=VALUE），注入当前进程环境变量。
        默认「已存在的非空进程环境变量优先」，便于 Linux systemd Environment= / 系统级变量覆盖（FR-12）。
        -Force 时 .env 覆盖已有值。只打印键名与数量，绝不打印值。
    #>
    param(
        [string]$Path = (Get-EnvFilePath),
        [switch]$Required,
        [switch]$Force
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        if ($Required) {
            throw ("未找到 .env 文件：" + $Path + "。请先复制 .env.example 为 .env 并填写配置。")
        }
        Write-Warn ("未找到 .env 文件：" + $Path + "；将仅使用进程已有环境变量。")
        return
    }

    $loaded = 0
    $skipped = 0
    $lineNo = 0
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    foreach ($line in $lines) {
        $lineNo++
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }

        # 只按第一个 '=' 分割，保证值中可含 '='（如连接串、Base64）
        $idx = $trimmed.IndexOf('=')
        if ($idx -lt 1) {
            Write-Warn (".env 第 " + $lineNo + " 行不是 KEY=VALUE 格式，已跳过。")
            continue
        }
        $name = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()

        # 去掉成对包裹的引号
        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        $existing = [Environment]::GetEnvironmentVariable($name, 'Process')
        if (-not $Force -and $null -ne $existing -and $existing -ne '') {
            $skipped++
            continue
        }
        Set-Item -Path ("env:" + $name) -Value $value -Force
        $loaded++
    }
    Write-Info (".env 加载完成：设置 " + $loaded + " 项，保留已有 " + $skipped + " 项（值不打印）。")
}

function Get-Config {
    param([Parameter(Mandatory = $true)][string]$Name, [string]$Default = '')
    $v = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -eq $v -or $v -eq '') { return $Default }
    return $v
}

function Test-EnvPlaceholder {
    param([Parameter(Mandatory = $true)][string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -eq $value) { return $true }
    $v = $value.Trim()
    if ($v -eq '') { return $true }
    foreach ($p in $script:PlaceholderPatterns) {
        if ($v.IndexOf($p, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Assert-RequiredEnv {
    <#
        硬校验：缺失或仍是占位符即 throw。启动类脚本（start-*.ps1 / run-worker.ps1 / backup/restore）必须调用。
        这对应 DEVOPS-02 与架构 §8：未配置返回 CONFIG_MISSING，不降级为假数据。
    #>
    param(
        [string[]]$Names = @('DATABASE_URL', 'SECRET_KEY'),
        [switch]$DetectPlaceholders
    )
    $missing = @()
    foreach ($n in $Names) {
        $v = [Environment]::GetEnvironmentVariable($n, 'Process')
        if ($null -eq $v -or $v.Trim() -eq '') { $missing += $n }
    }
    if ($missing.Count -gt 0) {
        throw ("CONFIG_MISSING：缺少必需环境变量 " + ($missing -join ', ') +
               "。请检查 .env；缺失项不得静默降级为 Mock / 假数据。")
    }
    if ($DetectPlaceholders) {
        $ph = @()
        foreach ($n in $Names) {
            if (Test-EnvPlaceholder -Name $n) { $ph += $n }
        }
        if ($ph.Count -gt 0) {
            throw ("CONFIG_MISSING：以下环境变量仍是占位符或明显未填写 " + ($ph -join ', ') +
                   "。请填入真实值；数据库凭据须由用户确认（BLK-05），外部密钥须经用户授权。")
        }
    }
    Write-Info ("必需环境变量校验通过：" + ($Names -join ', '))
}

function Write-EnvChecklist {
    <# 非阻断：setup.ps1 用，打印状态但不抛错（环境准备阶段允许 .env 仍为占位符）。 #>
    param([string[]]$Names = @('DATABASE_URL', 'SECRET_KEY'))
    Write-Info "必需环境变量状态（值不打印）："
    foreach ($n in $Names) {
        $v = [Environment]::GetEnvironmentVariable($n, 'Process')
        $state = 'SET'
        if ($null -eq $v -or $v.Trim() -eq '') { $state = 'MISSING' }
        elseif (Test-EnvPlaceholder -Name $n) { $state = 'PLACEHOLDER' }
        Write-Info ("  " + $n.PadRight(24) + " : " + $state)
    }
}

function Convert-ToHhmm {
    <# 把用户配置的时间归一化为零填充 HH:mm；非法值回落默认值并告警（UTC 语义由调用方保证）。 #>
    param([string]$Raw, [string]$Default)
    if ($Raw -match '^(\d{1,2}):(\d{1,2})$') {
        $h = [int]$Matches[1]
        $m = [int]$Matches[2]
        if ($h -ge 0 -and $h -le 23 -and $m -ge 0 -and $m -le 59) {
            return ('{0:D2}:{1:D2}' -f $h, $m)
        }
    }
    Write-Warn ("时间配置 '" + $Raw + "' 不是 HH:mm，改用默认值 " + $Default)
    return $Default
}

# ---------------------------------------------------------------- 命令与版本

function Assert-Command {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Hint = ''
    )
    $cmd = Get-Command -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        $msg = "CONFIG_MISSING：未找到命令 '" + $Name + "'。"
        if ($Hint -ne '') { $msg = $msg + " " + $Hint }
        throw $msg
    }
    Write-Info ("命令可用：" + $Name)
}

function Assert-PythonVersion {
    param([string]$PythonExe = 'python')
    $raw = & $PythonExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>&1
    if ($global:LASTEXITCODE -ne 0) {
        throw ("执行 " + $PythonExe + " 失败：" + ($raw -join ' '))
    }
    $text = [string]($raw | Select-Object -Last 1)
    $ver = [version]$text.Trim()
    if ($ver.Major -ne 3 -or $ver.Minor -ne 13) {
        throw ("需要 Python 3.13.x（backend/pyproject.toml: >=3.13,<3.14），实际为 " +
               $ver.ToString() + "。本机 py 启动器损坏，请统一使用 python。")
    }
    Write-Info ("Python 版本：" + $ver.ToString() + "（使用 python，未使用 py 启动器）")
}

function Assert-NodeVersion {
    $raw = & node --version 2>&1
    if ($global:LASTEXITCODE -ne 0) { throw ("执行 node --version 失败：" + ($raw -join ' ')) }
    $text = ([string]($raw | Select-Object -Last 1)).Trim().TrimStart('v')
    $ver = [version]$text
    if ($ver.Major -lt 22 -or $ver.Major -ge 25) {
        throw ("需要 Node 22–24（frontend/package.json engines: >=22 <25），实际 v" + $text + "。")
    }
    Write-Info ("Node 版本：v" + $text)
}

function Test-PortInUse {
    param([int]$Port, [string]$TargetHost = '127.0.0.1')
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(300, $false)
        if ($ok -and $client.Connected) { $client.Close(); return $true }
        $client.Close()
        return $false
    }
    catch { return $false }
}

# ---------------------------------------------------------------- 数据库迁移

function Invoke-AlembicUpgrade {
    <#
        执行 Alembic 迁移。仅在调用方显式要求（-RunMigrations）且 DATABASE_URL 已通过
        Assert-RequiredEnv 校验（非占位符）时才可调用；本次开发未执行任何真实迁移。
    #>
    param([Parameter(Mandatory = $true)][string]$PythonExe)
    $be = Get-BackendDir
    $ini = Join-Path $be 'alembic.ini'
    if (-not (Test-Path -LiteralPath $ini)) {
        throw ("未找到 Alembic 配置 " + $ini +
               "。迁移配置由 Backend Agent（BE-02）交付；交付前无法执行迁移，不得伪造成功。")
    }
    Write-Step "执行 Alembic 迁移：alembic upgrade head"
    Push-Location -LiteralPath $be
    try {
        & $PythonExe -m alembic upgrade head
        if ($global:LASTEXITCODE -ne 0) {
            throw ("Alembic 迁移失败（exit=" + $global:LASTEXITCODE + "）。")
        }
        Write-Info "Alembic 迁移完成。"
    }
    finally { Pop-Location }
}

# ---------------------------------------------------------------- PostgreSQL 凭据解析（备份/恢复用）

function Set-PostgresEnvFromUrl {
    <#
        把 DATABASE_URL（形如 postgresql+psycopg://user:pass@host:5432/dbname）
        解析为 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE 进程环境变量，供 pg_dump / pg_restore 使用。
        密码只进入进程环境变量，绝不打印。
    #>
    param([Parameter(Mandatory = $true)][string]$Url)

    $rest = $Url
    $schemeIdx = $Url.IndexOf('://')
    if ($schemeIdx -ge 0) { $rest = $Url.Substring($schemeIdx + 3) }

    $qIdx = $rest.IndexOf('?')
    if ($qIdx -ge 0) { $rest = $rest.Substring(0, $qIdx) }

    $userinfo = ''
    $atIdx = $rest.LastIndexOf('@')
    if ($atIdx -ge 0) {
        $userinfo = $rest.Substring(0, $atIdx)
        $rest = $rest.Substring($atIdx + 1)
    }

    $pgUser = ''
    $pgPass = ''
    if ($userinfo -ne '') {
        $cIdx = $userinfo.IndexOf(':')
        if ($cIdx -ge 0) {
            $pgUser = $userinfo.Substring(0, $cIdx)
            $pgPass = $userinfo.Substring($cIdx + 1)
        }
        else { $pgUser = $userinfo }
    }

    $pgHostPort = $rest
    $pgDb = ''
    $slash = $rest.IndexOf('/')
    if ($slash -ge 0) {
        $pgHostPort = $rest.Substring(0, $slash)
        $pgDb = $rest.Substring($slash + 1)
    }

    $pgHost = $pgHostPort
    $pgPort = '5432'
    $colon = $pgHostPort.LastIndexOf(':')
    if ($colon -ge 0) {
        $pgHost = $pgHostPort.Substring(0, $colon)
        $pgPort = $pgHostPort.Substring($colon + 1)
    }

    $pgUser = [System.Uri]::UnescapeDataString($pgUser)
    $pgPass = [System.Uri]::UnescapeDataString($pgPass)
    $pgDb   = [System.Uri]::UnescapeDataString($pgDb)

    if ($pgHost -eq '' -or $pgDb -eq '' -or $pgUser -eq '') {
        throw "DATABASE_URL 解析失败：无法得到 host / dbname / user 中的必需项，请检查格式（连接串不打印）。"
    }

    Set-Item -Path 'env:PGHOST'     -Value $pgHost -Force
    Set-Item -Path 'env:PGPORT'     -Value $pgPort -Force
    Set-Item -Path 'env:PGUSER'     -Value $pgUser -Force
    Set-Item -Path 'env:PGPASSWORD' -Value $pgPass -Force
    Set-Item -Path 'env:PGDATABASE' -Value $pgDb   -Force

    Write-Info ("PostgreSQL 目标：" + $pgUser + "@" + $pgHost + ":" + $pgPort + "/" + $pgDb + "（密码不打印）")
}

function Resolve-PgTool {
    <#
        定位 pg_dump / pg_restore。本机实测：二者不在 PATH，PostgreSQL 客户端工具未确认安装。
        因此找不到时明确报错并给出解决路径，绝不猜测或伪造备份结果。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$ExplicitPath = ''
    )
    if ($ExplicitPath -ne '') {
        if (Test-Path -LiteralPath $ExplicitPath) { return $ExplicitPath }
        throw ("指定的工具路径不存在：" + $ExplicitPath)
    }
    $cmd = Get-Command -Name $Name -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { return $cmd.Source }
    throw ("未找到 " + $Name + "。本机实测 pg_dump / psql / pg_restore 不在 PATH，且数据库凭据未确认（BLK-05）。" +
           "请安装 PostgreSQL 客户端工具并把其 bin 目录加入 PATH，或通过 -PgDumpPath / -PgRestorePath 指定 " +
           $Name + ".exe 的完整路径。本次未执行任何真实备份/恢复。")
}
