#Requires -Version 5.1
<#
    setup.ps1 — 本机一次性环境准备（DEVOPS-01 / DEVOPS-02 / DEVOPS-03）

    用法（在仓库根或任意目录均可，路径含空格已由 $PSScriptRoot 推导，无需硬编码）：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup.ps1" -RunMigrations

    职责：
        1) 校验本机已具备的运行时（Python 3.13 / Node 22 / pnpm），不安装系统级软件；
        2) 由 .env.example 生成 .env（若不存在）并加载；
        3) 创建 .venv、安装 backend/pyproject.toml 依赖、安装 frontend/package.json 依赖；
        4) 创建 logs / backups / data 目录（均已被 .gitignore 排除）；
        5) 可选执行 Alembic 迁移（默认关闭，避免误连本机 5432 上的未知实例）。

    硬约束提示：本脚本为「静态交付」。本次开发未运行它，未安装依赖、未联网、未启动服务、
    未连接数据库。执行脚本才会产生上述动作；数据库迁移与所有外部凭据均需用户确认/授权。
#>
[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$Force,
    [switch]$RunMigrations
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

$exitCode = 0
try {
    Start-ScriptLog -Name 'setup'
    Write-Step "=== AI Learning Memory OS / setup.ps1 ==="
    Write-Info ("仓库根：" + (Get-RepoRoot))
    Write-Warn "前提：当前 Windows 原生运行，不依赖 Docker / WSL / 虚拟机（FR-11）。"

    # ---- 1. 运行时校验（仅检查本机已具备的运行时，不做系统级安装/联网探测）----
    Write-Step "1/6 校验本机运行时"
    Assert-Command -Name 'python' -Hint '本机 py 启动器损坏（指向不存在的 C:\Python312\python.exe），必须使用 python。'
    Assert-PythonVersion -PythonExe 'python'
    Assert-Command -Name 'node'  -Hint '需要 Node.js 22.x（本机实测 v22.22.2）。'
    Assert-NodeVersion
    Assert-Command -Name 'pnpm'  -Hint '需要 pnpm 12.x（本机实测 12.18.0）。'

    # ---- 2. .env 准备与加载 ----
    Write-Step "2/6 准备 .env（密钥只从 .env / 环境变量读取，不入库不入 Git）"
    $envPath = Get-EnvFilePath
    if (-not (Test-Path -LiteralPath $envPath)) {
        $example = Join-Path (Get-RepoRoot) '.env.example'
        if (-not (Test-Path -LiteralPath $example)) {
            throw ("未找到 .env.example：" + $example)
        }
        Copy-Item -LiteralPath $example -Destination $envPath
        Write-Warn ("已由 .env.example 生成 .env：" + $envPath)
        Write-Warn "请填写真实配置（尤其 DATABASE_URL / SECRET_KEY）；未填写时启动类脚本会明确报错。"
    }
    Import-DotEnv -Path $envPath -Force:$Force

    # ---- 3. 运行时目录 ----
    Write-Step "3/6 创建运行时目录"
    $root = Get-RepoRoot
    foreach ($dirName in @('logs', 'backups', 'data')) {
        Ensure-Directory -Path (Join-Path $root $dirName)
    }

    # ---- 4. 后端 venv + 依赖 ----
    if (-not $SkipBackend) {
        Write-Step "4/6 创建 .venv 并安装后端依赖（来源：backend/pyproject.toml）"
        $venv = Join-Path $root '.venv'
        $py = Get-VenvPython
        if ($null -eq $py) {
            Write-Info ("创建虚拟环境：" + $venv)
            & python -m venv $venv
            if ($global:LASTEXITCODE -ne 0) {
                throw ("python -m venv 失败（exit=" + $global:LASTEXITCODE + "）。")
            }
            $py = Get-VenvPython
            if ($null -eq $py) { throw ("venv 已创建但未找到解释器，请检查 " + $venv) }
        }
        Write-Info ("使用虚拟环境解释器：" + $py)

        Push-Location -LiteralPath (Get-BackendDir)
        try {
            Write-Info "升级 pip ..."
            & $py -m pip install --upgrade pip
            if ($global:LASTEXITCODE -ne 0) { throw "升级 pip 失败。" }
            Write-Info "安装后端依赖：pip install -e .[dev,test]"
            & $py -m pip install -e '.[dev,test]'
            if ($global:LASTEXITCODE -ne 0) { throw "后端依赖安装失败。" }
        }
        finally { Pop-Location }
        Write-Info "后端依赖安装完成。"
    }
    else {
        Write-Warn "已跳过后端依赖安装（-SkipBackend）。"
    }

    # ---- 5. 前端依赖 ----
    if (-not $SkipFrontend) {
        Write-Step "5/6 安装前端依赖（来源：frontend/package.json）"
        $fe = Get-FrontendDir
        Push-Location -LiteralPath $fe
        try {
            $lock = Join-Path $fe 'pnpm-lock.yaml'
            if (Test-Path -LiteralPath $lock) {
                Write-Info "检测到 pnpm-lock.yaml，使用 --frozen-lockfile"
                & pnpm install --frozen-lockfile
            }
            else {
                Write-Warn "未发现 pnpm-lock.yaml，使用普通 pnpm install（将生成锁文件）。"
                & pnpm install
            }
            if ($global:LASTEXITCODE -ne 0) { throw "前端依赖安装失败。" }
        }
        finally { Pop-Location }
        Write-Info "前端依赖安装完成。"
    }
    else {
        Write-Warn "已跳过前端依赖安装（-SkipFrontend）。"
    }

    # ---- 6. 配置状态（非阻断）与可选迁移 ----
    Write-Step "6/6 配置检查与可选迁移"
    Write-EnvChecklist
    Write-Warn "启动前必须把 DATABASE_URL / SECRET_KEY 从 PLACEHOLDER 改为真实值；"
    Write-Warn "外部凭据（Notion / LLM / 通知渠道）需用户授权，未配置时相关功能明确报错（不返回假数据）。"

    if ($RunMigrations) {
        $py = Get-VenvPython
        if ($null -eq $py) {
            throw "未找到 .venv 解释器，请先运行 setup.ps1（不带 -SkipBackend）。"
        }
        Write-Warn "即将执行 Alembic 迁移：请确认 DATABASE_URL 指向用户已确认的 PostgreSQL 实例（BLK-05）。"
        Assert-RequiredEnv -DetectPlaceholders
        Invoke-AlembicUpgrade -PythonExe $py
    }
    else {
        Write-Warn "已跳过数据库迁移（默认）。确认凭据后可用：setup.ps1 -RunMigrations 或 start-backend.ps1 -RunMigrations"
    }

    Write-Step "setup.ps1 完成。下一步：按 DEPLOYMENT.md 启动前后端与后台任务。"
}
catch {
    Write-Err ("setup.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
