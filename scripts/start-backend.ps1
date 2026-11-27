#Requires -Version 5.1
<#
    start-backend.ps1 — 启动 FastAPI 后端（uvicorn），DEVOPS-03 / FR-11

    用法：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-backend.ps1"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-backend.ps1" -RunMigrations
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-backend.ps1" -Reload

    前置：先运行 setup.ps1（.venv 与依赖已就绪），并在 .env 填好 DATABASE_URL / SECRET_KEY。
    端口：APP_HOST / APP_PORT 来自 .env（环境变量化，FR-12 不写死 Windows 路径/端口）。
    ASGI 入口：UVICORN_APP（默认 app.main:app），可由 -AppModule 覆盖；由 Backend Agent（BE-01）交付。

    本次开发为静态交付：未启动任何服务、未连接数据库、未执行迁移。
#>
[CmdletBinding()]
param(
    [switch]$RunMigrations,
    [switch]$Reload,
    [string]$AppModule = ''
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

$exitCode = 0
try {
    Start-ScriptLog -Name 'start-backend'
    Write-Step "=== start-backend.ps1 ==="

    Import-DotEnv -Path (Get-EnvFilePath) -Required
    Assert-RequiredEnv -DetectPlaceholders

    $py = Get-VenvPython
    if ($null -eq $py) {
        throw "未找到 .venv 解释器。请先运行 scripts/setup.ps1（不带 -SkipBackend）。"
    }
    Write-Info ("虚拟环境解释器：" + $py)

    $bindHost = Get-Config -Name 'APP_HOST' -Default '127.0.0.1'
    $port = [int](Get-Config -Name 'APP_PORT' -Default '8000')
    $module = $AppModule
    if ($module -eq '') {
        $module = Get-Config -Name 'UVICORN_APP' -Default 'app.main:app'
    }

    if (Test-PortInUse -Port $port -TargetHost $bindHost) {
        throw ("端口 " + $port + " (" + $bindHost + ") 已被占用。请修改 .env 的 APP_PORT 或停止占用进程。")
    }

    if ($RunMigrations) {
        Write-Step "启动前执行 Alembic 迁移"
        Invoke-AlembicUpgrade -PythonExe $py
    }
    else {
        Write-Warn "未执行 Alembic 迁移。首次启动或模型变更后请加 -RunMigrations（需已确认的数据库凭据）。"
    }

    Write-Info ("启动 uvicorn：" + $module + " @ " + $bindHost + ":" + $port)
    Push-Location -LiteralPath (Get-BackendDir)
    try {
        $uvicornArgs = @('-m', 'app.server', $module, '--host', $bindHost, '--port', "$port")
        if ($Reload) {
            $uvicornArgs += '--reload'
            Write-Warn "开发模式：--reload 已启用（生产部署请勿使用）。"
        }
        & $py @uvicornArgs
        $code = $global:LASTEXITCODE
        if ($code -ne 0) {
            throw ("uvicorn 退出（exit=" + $code + "）。请确认后端入口 " + $module +
                   " 已由 Backend Agent 交付、依赖已安装、且数据库凭据有效。")
        }
    }
    finally { Pop-Location }
    Write-Step "后端进程已退出。"
}
catch {
    Write-Err ("start-backend.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
