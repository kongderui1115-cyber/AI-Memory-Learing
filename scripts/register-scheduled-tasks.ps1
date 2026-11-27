#Requires -Version 5.1
<#
    register-scheduled-tasks.ps1 — Windows 任务计划注册（DEVOPS-04 / FR-11）

    用 Windows 任务计划程序触发 run-worker.ps1 的单次任务，**不依赖 WSL / Docker / 常驻进程**。
    注册的三个任务（前缀默认 AILMOS）：
        AILMOS-NotionSync   每 NOTION_SYNC_INTERVAL_MINUTES 分钟  -> -Job sync-notion
        AILMOS-DailyTasks   每天 DAILY_TASKS_AT (UTC)             -> -Job generate-daily-tasks
        AILMOS-DailyDigest  每天 DAILY_DIGEST_AT (UTC)            -> -Job send-daily-digest

    用法（默认仅预览，不产生任何系统变更）：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\register-scheduled-tasks.ps1"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\register-scheduled-tasks.ps1" -List
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\register-scheduled-tasks.ps1" -Apply
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\register-scheduled-tasks.ps1" -Apply -Unregister

    安全门槛：注册/注销属于系统级变更，必须显式给 -Apply；默认只打印计划。
    路径含空格：动作命令行中的脚本路径整体用双引号包裹（由 Start/Action 构造）。
    Linux 替换：见 infra/systemd/*.timer 与 infra/cron/ailmos.crontab（DEVOPS-04 / FR-12）。

    ⛔ 本次开发为静态交付：未注册 / 未注销任何系统任务，未查询系统任务状态。
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Unregister,
    [switch]$List,
    [string]$TaskPrefix = 'AILMOS',
    [int]$SyncIntervalMinutes = 0,
    [string]$DailyTasksAt = '',
    [string]$DailyDigestAt = '',
    [string]$RunAsUser = ''
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

function New-DailyTrigger {
    param([Parameter(Mandatory = $true)][string]$At)
    $parts = $At.Split(':')
    $h = [int]$parts[0]
    $m = [int]$parts[1]
    $dt = Get-Date -Hour $h -Minute $m -Second 0 -Millisecond 0
    return New-ScheduledTaskTrigger -Daily -At $dt
}

function New-IntervalTrigger {
    param([int]$Minutes)
    $start = (Get-Date).AddMinutes(1)
    return New-ScheduledTaskTrigger -Once -At $start `
        -RepetitionInterval (New-TimeSpan -Minutes $Minutes) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
}

$exitCode = 0
try {
    Start-ScriptLog -Name 'register-scheduled-tasks'
    Write-Step "=== register-scheduled-tasks.ps1 ==="

    # 模块可用性（Windows PowerShell 5.1 自带 ScheduledTasks 模块）
    $mod = @(Get-Module -ListAvailable -Name ScheduledTasks)
    if ($mod.Count -eq 0) {
        throw ("未找到 ScheduledTasks PowerShell 模块。请改用 schtasks.exe，或在 Windows PowerShell 5.1 中运行本脚本。")
    }
    Import-Module ScheduledTasks -ErrorAction Stop

    Import-DotEnv -Path (Get-EnvFilePath)

    $user = $RunAsUser
    if ($user -eq '') { $user = [Environment]::GetEnvironmentVariable('USERNAME', 'Process') }
    if ($null -eq $user -or $user -eq '') {
        throw "无法确定运行账户，请通过 -RunAsUser 指定。"
    }

    if ($SyncIntervalMinutes -le 0) {
        $SyncIntervalMinutes = [int](Get-Config -Name 'NOTION_SYNC_INTERVAL_MINUTES' -Default '60')
    }
    if ($SyncIntervalMinutes -le 0) { $SyncIntervalMinutes = 60 }
    if ($DailyTasksAt -eq '')  { $DailyTasksAt = Get-Config -Name 'DAILY_TASKS_AT'  -Default '00:05' }
    if ($DailyDigestAt -eq '') { $DailyDigestAt = Get-Config -Name 'DAILY_DIGEST_AT' -Default '08:00' }
    $tasksAt  = Convert-ToHhmm -Raw $DailyTasksAt  -Default '00:05'
    $digestAt = Convert-ToHhmm -Raw $DailyDigestAt -Default '08:00'

    # ---- 仅列出已注册的同类任务 ----
    if ($List) {
        Write-Info ("列出任务名以 '" + $TaskPrefix + "' 开头的计划任务：")
        $found = @(Get-ScheduledTask -TaskName ($TaskPrefix + '*') -ErrorAction SilentlyContinue)
        if ($found.Count -eq 0) {
            Write-Warn "未找到任何匹配的计划任务。"
        }
        else {
            foreach ($t in $found) {
                Write-Info ("  " + $t.TaskName + " : " + $t.State)
            }
        }
    }
    else {
        $psExe = (Get-Command powershell.exe).Source
        $worker = Join-Path $PSScriptRoot 'run-worker.ps1'
        if (-not (Test-Path -LiteralPath $worker)) { throw ("缺少 worker 脚本：" + $worker) }

        $taskDefs = @(
            [pscustomobject]@{ name = $TaskPrefix + '-NotionSync';  job = 'sync-notion';          kind = 'interval'; at = '' }
            [pscustomobject]@{ name = $TaskPrefix + '-DailyTasks';  job = 'generate-daily-tasks'; kind = 'daily';    at = $tasksAt }
            [pscustomobject]@{ name = $TaskPrefix + '-DailyDigest'; job = 'send-daily-digest';    kind = 'daily';    at = $digestAt }
        )

        foreach ($def in $taskDefs) {
            # -File 路径含空格，整体加双引号
            $arg = '-NoProfile -ExecutionPolicy Bypass -File "' + $worker + '" -Job ' + $def.job
            $action = New-ScheduledTaskAction -Execute $psExe -Argument $arg
            $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
            $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -StartWhenAvailable

            if ($def.kind -eq 'interval') {
                $trigger = New-IntervalTrigger -Minutes $SyncIntervalMinutes
                $triggerDesc = "每 " + $SyncIntervalMinutes + " 分钟重复（Once + RepetitionInterval）"
            }
            else {
                $trigger = New-DailyTrigger -At $def.at
                $triggerDesc = "每天 " + $def.at + "（本机本地时间；业务内部按 UTC 处理）"
            }

            Write-Info ("任务：" + $def.name)
            Write-Info ("  命令行：" + $psExe + " " + $arg)
            Write-Info ("  触发器：" + $triggerDesc)
            Write-Info ("  运行账户：" + $user + " / LogonType=Interactive / RunLevel=Limited")

            if ($Apply) {
                if ($Unregister) {
                    Write-Warn ("注销任务：" + $def.name)
                    Unregister-ScheduledTask -TaskName $def.name -Confirm:$false -ErrorAction Stop
                }
                else {
                    Write-Warn ("注册任务：" + $def.name + "（系统级变更，-Apply 已显式给出）")
                    Register-ScheduledTask -TaskName $def.name -Action $action -Trigger $trigger `
                        -Principal $principal -Settings $settings `
                        -Description ("AI Learning Memory OS worker: " + $def.job) -Force -ErrorAction Stop | Out-Null
                    Write-Info ("已注册：" + $def.name)
                }
            }
        }

        if (-not $Apply) {
            Write-Step "预览模式：以上仅为将要注册的内容，未对系统做任何变更。"
            Write-Warn "确认无误后加 -Apply 才实际注册；系统级变更需用户授权。"
            if ($Unregister) { Write-Warn "检测到 -Unregister，但缺少 -Apply，故未执行注销。" }
        }
        else {
            if ($Unregister) { Write-Step "注销完成。" }
            else { Write-Step "注册完成。可用 -List 复查；用 start-all.ps1 -WithWorker 或任务计划触发 worker。" }
        }
    }
}
catch {
    Write-Err ("register-scheduled-tasks.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
