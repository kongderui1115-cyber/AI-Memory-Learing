#Requires -Version 5.1
<#
    start-all.ps1 — 一键启动前后端（可选常驻 worker），DEVOPS-03 / DEVOPS-04 / FR-11

    用法：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-all.ps1"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-all.ps1" -WithWorker
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-all.ps1" -Stop

    行为：
        - 用 Start-Process 分别拉起独立的 PowerShell 5.1 进程运行 start-backend.ps1 /
          start-frontend.ps1（各自用 Transcript 写 logs/），互不阻塞；
        - 把子进程 PID 记录到 data/start-all.pids.json（已 gitignore），供 -Stop 精确停止；
        - 启动前检查 APP_PORT / FRONTEND_PORT 是否被占用，避免静默失败；
        - -WithWorker 额外拉起 run-worker.ps1 -Loop（纯 PowerShell 常驻循环，不依赖 WSL/Docker/APScheduler）。

    系统级任务计划注册是另一回事（会修改系统状态），不在此脚本内自动执行；
    请按 DEPLOYMENT.md 自行运行 scripts/register-scheduled-tasks.ps1（需用户授权）。

    本次开发为静态交付：未启动任何进程、未注册任何系统任务。
#>
[CmdletBinding()]
param(
    [switch]$Stop,
    [switch]$WithWorker,
    [ValidateSet('dev', 'build', 'start')][string]$FrontendMode = 'dev'
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

$dataDir = Join-Path (Get-RepoRoot) 'data'
$pidFile = Join-Path $dataDir 'start-all.pids.json'

function Stop-StartedProcesses {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        Write-Warn "没有 PID 记录文件，无需停止。"
        return
    }
    $raw = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8
    $records = @(ConvertFrom-Json -InputObject $raw)
    foreach ($r in $records) {
        $proc = Get-Process -Id $r.processId -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            Write-Info ("停止进程 " + $r.name + " (PID " + $r.processId + ")")
            Stop-Process -Id $r.processId -Force -ErrorAction SilentlyContinue
        }
        else {
            Write-Warn ("进程 " + $r.name + " (PID " + $r.processId + ") 已不存在。")
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
    Write-Info "已清理 PID 记录。"
}

$exitCode = 0
try {
    Start-ScriptLog -Name 'start-all'

    if ($Stop) {
        Write-Step "=== start-all.ps1 -Stop ==="
        Stop-StartedProcesses
    }
    else {
        Write-Step "=== start-all.ps1（一键启动）==="
        Import-DotEnv -Path (Get-EnvFilePath) -Required
        Assert-RequiredEnv -DetectPlaceholders
        Ensure-Directory -Path $dataDir
        Ensure-Directory -Path (Join-Path (Get-RepoRoot) 'logs')

        $bePort = [int](Get-Config -Name 'APP_PORT' -Default '8000')
        $fePort = [int](Get-Config -Name 'FRONTEND_PORT' -Default '3030')
        if (Test-PortInUse -Port $bePort -TargetHost '127.0.0.1') {
            throw ("后端端口 " + $bePort + " 已被占用（APP_PORT）。")
        }
        if (Test-PortInUse -Port $fePort -TargetHost '127.0.0.1') {
            throw ("前端端口 " + $fePort + " 已被占用（FRONTEND_PORT）。")
        }

        $psExe = (Get-Command powershell.exe).Source
        $backendScript  = Join-Path $PSScriptRoot 'start-backend.ps1'
        $frontendScript = Join-Path $PSScriptRoot 'start-frontend.ps1'
        $workerScript   = Join-Path $PSScriptRoot 'run-worker.ps1'

        foreach ($p in @($backendScript, $frontendScript, $workerScript)) {
            if (-not (Test-Path -LiteralPath $p)) { throw ("缺少脚本：" + $p) }
        }

        $records = @()

        # 后端
        $beArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $backendScript + '"'
        $beProc = Start-Process -FilePath $psExe -ArgumentList $beArgs -PassThru -WindowStyle Hidden
        $records += [pscustomobject]@{ name = 'backend';  processId = $beProc.Id }
        Write-Info ("已启动后端 (PID " + $beProc.Id + ")")

        # 前端：模式由 -FrontendMode 传入（dev 默认；生产需先 -Mode build 再 -FrontendMode start）
        $feArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $frontendScript + '" -Mode ' + $FrontendMode
        $feProc = Start-Process -FilePath $psExe -ArgumentList $feArgs -PassThru -WindowStyle Hidden
        $records += [pscustomobject]@{ name = 'frontend'; processId = $feProc.Id }
        Write-Info ("已启动前端 (PID " + $feProc.Id + ")，模式 " + $FrontendMode)

        # 可选常驻 worker
        if ($WithWorker) {
            $wArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $workerScript + '" -Loop'
            $wProc = Start-Process -FilePath $psExe -ArgumentList $wArgs -PassThru -WindowStyle Hidden
            $records += [pscustomobject]@{ name = 'worker'; processId = $wProc.Id }
            Write-Info ("已启动常驻 worker (PID " + $wProc.Id + ")")
        }

        $records | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $pidFile -Encoding UTF8
        Write-Info ("PID 记录：" + $pidFile)
        Write-Step "一键启动完成。使用 start-all.ps1 -Stop 停止以上进程。"
        Write-Warn "系统级定时任务需另行注册：scripts/register-scheduled-tasks.ps1（需用户授权）。"
    }
}
catch {
    Write-Err ("start-all.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
