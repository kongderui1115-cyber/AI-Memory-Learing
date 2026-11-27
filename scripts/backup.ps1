#Requires -Version 5.1
<#
    backup.ps1 — PostgreSQL 逻辑备份（DEVOPS-05 / FR-12）

    用法：
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\backup.ps1"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\backup.ps1" -Format plain -OutputDir "D:\bak"
        powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\backup.ps1" -PgDumpPath "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"

    凭据：从 .env 的 DATABASE_URL 解析为 PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE 进程环境变量，
    密码不打印、不写日志、不入库、不入 Git。占位符连接串会被拒绝（不擅自连接未知实例）。

    ⛔ 未演练（如实标注）：本机实测 pg_dump / psql 不在 PATH，且 5432 上未知实例的凭据未确认（BLK-05）。
       本脚本为静态交付，本次开发未执行过真实备份、未连接任何数据库、未产生任何备份文件。
       演练前 DEPLOYMENT.md / TEST_REPORT.md 中备份恢复项必须保持「未执行」。
#>
[CmdletBinding()]
param(
    [string]$OutputDir = '',
    [ValidateSet('custom', 'plain', 'tar')][string]$Format = 'custom',
    [string]$PgDumpPath = ''
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

$exitCode = 0
try {
    Start-ScriptLog -Name 'backup'
    Write-Step "=== backup.ps1（DEVOPS-05）==="
    Write-Warn "⛔ 未演练：pg_dump 不在 PATH 且数据库凭据未确认（BLK-05）；本次未执行真实备份。"

    Import-DotEnv -Path (Get-EnvFilePath) -Required
    Assert-RequiredEnv -DetectPlaceholders

    $dbUrl = Get-Config -Name 'DATABASE_URL'
    Set-PostgresEnvFromUrl -Url $dbUrl

    $dump = Resolve-PgTool -Name 'pg_dump' -ExplicitPath $PgDumpPath
    Write-Info ("pg_dump：" + $dump)

    if ($OutputDir -eq '') { $OutputDir = Join-Path (Get-RepoRoot) 'backups' }
    Ensure-Directory -Path $OutputDir

    $dbName = [Environment]::GetEnvironmentVariable('PGDATABASE', 'Process')
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $ext = '.dump'
    if ($Format -eq 'plain') { $ext = '.sql' }
    if ($Format -eq 'tar')   { $ext = '.tar' }
    $outFile = Join-Path $OutputDir ("ailmos-" + $dbName + "-" + $stamp + $ext)

    Write-Step ("开始备份 -> " + $outFile + "（格式 " + $Format + "）")
    & $dump "--format=$Format" --no-owner --no-privileges --file $outFile
    $code = $global:LASTEXITCODE
    if ($code -ne 0) {
        throw ("pg_dump 失败（exit=" + $code + "）。请检查连接凭据、目标库与磁盘权限。")
    }

    if (-not (Test-Path -LiteralPath $outFile)) {
        throw ("pg_dump 返回成功但未生成备份文件：" + $outFile)
    }
    $item = Get-Item -LiteralPath $outFile
    if ($item.Length -le 0) {
        throw ("备份文件为空：" + $outFile)
    }
    Write-Info ("备份完成：" + $outFile + "（" + $item.Length + " 字节）")
    Write-Step "backup.ps1 完成。"
}
catch {
    Write-Err ("backup.ps1 失败：" + $_.Exception.Message)
    $exitCode = 1
}
finally {
    Stop-ScriptLog
}
exit $exitCode
