#Requires -Version 5.1
<#
    start-frontend.ps1 — 启动 Next.js 前端，DEVOPS-03 / FR-11

    用法：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-frontend.ps1"              # dev
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-frontend.ps1" -Mode build  # 构建
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-frontend.ps1" -Mode start  # 生产启动（需先 build）
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-frontend.ps1" -Port 3100

    前置：先运行 setup.ps1（frontend/node_modules 已就绪）。
    端口为 FRONTEND_PORT（默认 3030），同源 API 由 Next.js 转发到 BACKEND_API_URL。
    全部来自 .env，环境变量化（FR-12）。

    本次开发为静态交付：未启动任何服务、未执行构建。
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'build', 'start')][string]$Mode = 'dev',
    [int]$Port = 0
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

$exitCode = 0
try {
    Start-ScriptLog -Name 'start-frontend'
    Write-Step "=== start-frontend.ps1 ==="

    Import-DotEnv -Path (Get-EnvFilePath) -Required
    Assert-Command -Name 'pnpm' -Hint '需要 pnpm 12.x（本机实测 12.18.0）。'

    $fe = Get-FrontendDir
    $nodeModules = Join-Path $fe 'node_modules'
    if (-not (Test-Path -LiteralPath $nodeModules)) {
        throw ("frontend/node_modules 不存在：" + $nodeModules + "。请先运行 scripts/setup.ps1。")
    }

    if ($Port -le 0) {
        $Port = [int](Get-Config -Name 'FRONTEND_PORT' -Default '3030')
    }
    $apiBase = Get-Config -Name 'BACKEND_API_URL' -Default 'http://127.0.0.1:8000'
    $env:BACKEND_API_URL = $apiBase
    Write-Info ("前端端口：" + $Port + "；后端 API 基址：" + $apiBase)

    if ($Mode -ne 'build' -and (Test-PortInUse -Port $Port -TargetHost '127.0.0.1')) {
        throw ("端口 " + $Port + " 已被占用。请调整 .env 的 FRONTEND_PORT 或传入 -Port。")
    }

    if ($Mode -eq 'start') {
        $buildDir = Join-Path $fe '.next'
        if (-not (Test-Path -LiteralPath $buildDir)) {
            throw ("未发现构建产物 " + $buildDir + "。请先执行 -Mode build 再 -Mode start。")
        }
    }

    Push-Location -LiteralPath $fe
    try {
        switch ($Mode) {
            'dev'   { Write-Step ("pnpm dev -p " + $Port);   & pnpm dev   -H 127.0.0.1 -p $Port }
            'build' { Write-Step "pnpm build";               & pnpm build }
            'start' { Write-Step ("pnpm start -p " + $Port); & pnpm start -H 127.0.0.1 -p $Port }
        }
        if ($global:LASTEXITCODE -ne 0) {
            throw ("pnpm " + $Mode + " 失败（exit=" + $global:LASTEXITCODE + "）。")
        }
    }
    finally { Pop-Location }
    Write-Step ("前端进程已退出（模式 " + $Mode + "）。")
}
catch {
    Write-Err ("start-frontend.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
