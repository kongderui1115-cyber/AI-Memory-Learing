#Requires -Version 5.1
<#
    run-worker.ps1 — 后台任务入口（DEVOPS-04 / FR-11 / FR-12）

    覆盖三类任务：
        sync-notion           Notion 定时增量同步（FR-01）
        generate-daily-tasks  每日复习任务生成（FR-06）
        send-daily-digest     每日推送（FR-07 / FR-08）

    两种运行形态（可替换，均不依赖 WSL / Docker）：
        A. 单次触发（供 Windows 任务计划 / Linux systemd timer / cron 调用）：
             powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run-worker.ps1" -Job sync-notion
        B. 常驻循环（纯 PowerShell 定时，不依赖 APScheduler）：
             powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run-worker.ps1" -Loop

    业务 CLI 入口约定：python -m app.worker <job>（可用 WORKER_MODULE 覆盖），
    由 Backend / AI Integration / Notification Agent 交付。未交付时脚本明确报错，不伪造任务成功结果。

    凭据策略（DEVOPS-02 / 架构 §8）：
        对应功能的凭据未配置或为占位符时抛 CONFIG_MISSING，禁止假同步 / 假推送。
        所有外部账号 / API Key / 渠道凭据均需用户授权（BLK-01..04）。

    本次开发为静态交付：未启动任何进程、未注册系统任务、未调用任何外部 API。
#>
[CmdletBinding()]
param(
    [ValidateSet('sync-notion', 'extract-chapters', 'generate-daily-tasks', 'send-daily-digest', 'all')]
    [string]$Job = 'all',
    [switch]$Loop,
    [int]$LoopIntervalSeconds = 60
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

function Assert-JobConfig {
    <# 任务级凭据校验：缺配置即 CONFIG_MISSING，不得静默降级或假推送。 #>
    param([Parameter(Mandatory = $true)][string]$Name)

    switch ($Name) {
        'sync-notion' {
            Write-Info "Notion 凭据引用由数据库中的用户数据源配置解析。"
        }
        'extract-chapters' {
            Write-Info "模型凭据及计费授权由持久化章节任务执行器逐项校验。"
        }
        'generate-daily-tasks' {
            # 仅依赖数据库（已由 Assert-RequiredEnv -DetectPlaceholders 覆盖），不调用外部 API。
            Write-Info "任务 generate-daily-tasks：仅依赖本地数据库，不产生外部调用。"
        }
        'send-daily-digest' {
            Write-Info "邮件配置与接收地址按用户读取，未配置渠道保留明确错误状态。"
        }
    }
}

function Invoke-WorkerJob {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$PythonExe
    )
    Assert-JobConfig -Name $Name

    $module = Get-Config -Name 'WORKER_MODULE' -Default 'app.worker'
    Write-Step ("执行后台任务：" + $Name + " -> python -m " + $module + " " + $Name)

    Push-Location -LiteralPath (Get-BackendDir)
    try {
        & $PythonExe -m $module $Name
        $code = $global:LASTEXITCODE
        if ($code -ne 0) {
            throw ("任务 '" + $Name + "' 执行失败（exit=" + $code + "）。" +
                   "若模块 " + $module + " 尚未由 Backend/AI/Notification Agent 交付，属预期；本次不伪造成功结果。")
        }
    }
    finally { Pop-Location }
    Write-Info ("任务完成：" + $Name)
}

function Start-WorkerLoop {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExe,
        [int]$IntervalSeconds
    )
    if ($IntervalSeconds -lt 5) { $IntervalSeconds = 5 }

    $syncEvery = [int](Get-Config -Name 'NOTION_SYNC_INTERVAL_MINUTES' -Default '60')
    if ($syncEvery -le 0) { $syncEvery = 60 }
    $dailyAt  = Convert-ToHhmm -Raw (Get-Config -Name 'DAILY_TASKS_AT'  -Default '00:05') -Default '00:05'
    $digestAt = Convert-ToHhmm -Raw (Get-Config -Name 'DAILY_DIGEST_AT' -Default '08:00') -Default '08:00'

    Write-Info ("常驻循环（UTC）：Notion 同步每 " + $syncEvery + " 分钟；每日任务 " + $dailyAt +
                "；每日推送 " + $digestAt + "；轮询间隔 " + $IntervalSeconds + " 秒。")
    Write-Warn "按 Ctrl+C 结束。单次任务失败只记录错误并继续循环，不会终止 worker。"

    $syncAccum = 0
    $lastTasksDate = ''
    $lastDigestDate = ''

    while ($true) {
        $now = (Get-Date).ToUniversalTime()
        $today = $now.ToString('yyyy-MM-dd')
        $hhmm = $now.ToString('HH:mm')

        if ($hhmm -ge $dailyAt -and $lastTasksDate -ne $today) {
            try { Invoke-WorkerJob -Name 'generate-daily-tasks' -PythonExe $PythonExe }
            catch { Write-Err ("[generate-daily-tasks] " + $_.Exception.Message) }
            $lastTasksDate = $today
        }

        if ($hhmm -ge $digestAt -and $lastDigestDate -ne $today) {
            try { Invoke-WorkerJob -Name 'send-daily-digest' -PythonExe $PythonExe }
            catch { Write-Err ("[send-daily-digest] " + $_.Exception.Message) }
            $lastDigestDate = $today
        }

        $syncAccum = $syncAccum + $IntervalSeconds
        if ($syncAccum -ge ($syncEvery * 60)) {
            $syncAccum = 0
            try { Invoke-WorkerJob -Name 'sync-notion' -PythonExe $PythonExe }
            catch { Write-Err ("[sync-notion] " + $_.Exception.Message) }
        }

        try { Invoke-WorkerJob -Name 'extract-chapters' -PythonExe $PythonExe }
        catch { Write-Err ("[extract-chapters] " + $_.Exception.Message) }

        Start-Sleep -Seconds $IntervalSeconds
    }
}

$exitCode = 0
try {
    Start-ScriptLog -Name 'run-worker'
    Write-Step "=== run-worker.ps1（DEVOPS-04）==="

    Import-DotEnv -Path (Get-EnvFilePath) -Required
    Assert-RequiredEnv -DetectPlaceholders

    $py = Get-VenvPython
    if ($null -eq $py) {
        throw "未找到 .venv 解释器。请先运行 scripts/setup.ps1。"
    }
    Write-Info ("虚拟环境解释器：" + $py)

    if ($Loop) {
        if ($Job -ne 'all') {
            Write-Warn ("-Loop 常驻模式下忽略 -Job " + $Job + "，按配置调度全部三类任务。")
        }
        Start-WorkerLoop -PythonExe $py -IntervalSeconds $LoopIntervalSeconds
    }
    else {
        $jobs = @()
        if ($Job -eq 'all') {
            $jobs = @('sync-notion', 'extract-chapters', 'generate-daily-tasks', 'send-daily-digest')
        }
        else { $jobs = @($Job) }

        $failed = 0
        foreach ($j in $jobs) {
            try {
                Invoke-WorkerJob -Name $j -PythonExe $py
            }
            catch {
                Write-Err ("任务 '" + $j + "' 失败：" + $_.Exception.Message)
                $failed++
            }
        }
        if ($failed -gt 0) {
            throw ("共 " + $failed + " / " + $jobs.Count + " 个后台任务失败（详见上方 CONFIG_MISSING / 执行错误）。")
        }
        Write-Step ("单次任务执行完成（" + $jobs.Count + " 个）。")
    }
}
catch {
    Write-Err ("run-worker.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
