#Requires -Version 5.1
<#
    Restore a trusted PostgreSQL custom or tar archive into an empty staging database.
    Set RESTORE_DATABASE_URL in the calling process. The target must end in _restore.
    See docs/BACKUP_RESTORE.md for prerequisites and verification.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$PgRestorePath = '',
    [string]$PsqlPath = ''
)

. (Join-Path $PSScriptRoot 'lib/common.ps1')

function Get-DatabaseConnection {
    param([string]$Url, [string]$Config)
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -notmatch '^postgres(ql)?(\+psycopg2?)?$' -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or $uri.Fragment) {
        throw "$Config must be a PostgreSQL connection URL with a host and database name."
    }
    $name = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if (-not $name -or $name.Contains('/')) {
        throw "$Config must name exactly one database."
    }
    return [pscustomobject]@{ Uri = $uri; Name = $name }
}

function Invoke-DatabaseTool {
    param([string]$Tool, [string[]]$Arguments)
    # PowerShell 5.1 treats native stderr as an error record even when redirected.
    # Keep native diagnostics out of transcript/error messages and check the native exit code.
    $ErrorActionPreference = 'Continue'
    $global:LASTEXITCODE = 1
    $output = & $Tool @Arguments 2>$null
    return [pscustomobject]@{ Code = $LASTEXITCODE; Output = @($output) }
}

$exitCode = 1
$previousEnv = @{}
try {
    $restoreUrl = Get-Config -Name 'RESTORE_DATABASE_URL'
    if (-not $restoreUrl -or (Test-EnvPlaceholder -Name 'RESTORE_DATABASE_URL')) {
        throw 'Set RESTORE_DATABASE_URL in the process environment to a dedicated staging database.'
    }
    $target = Get-DatabaseConnection -Url $restoreUrl -Config 'RESTORE_DATABASE_URL'
    if ($target.Name -cnotmatch '^[a-z][a-z0-9_]{0,54}_restore$' -or $target.Uri.Query) {
        throw 'The restore database must be a dedicated lowercase name ending in _restore. URL query parameters are unsupported.'
    }

    $applicationUrl = Get-Config -Name 'DATABASE_URL'
    if (-not $applicationUrl) {
        $envFile = Get-EnvFilePath
        if (Test-Path -LiteralPath $envFile -PathType Leaf) {
            $setting = Select-String -LiteralPath $envFile -Pattern '^\s*(?:export\s+)?DATABASE_URL\s*=' | Select-Object -Last 1
            if ($setting) {
                $applicationUrl = ($setting.Line -split '=', 2)[1].Trim().Trim('"', "'")
            }
        }
    }
    if (-not $applicationUrl) {
        throw 'Set the current application DATABASE_URL or its normal .env so the restore target can be compared.'
    }
    $application = Get-DatabaseConnection -Url $applicationUrl -Config 'DATABASE_URL'
    if ([Uri]::UnescapeDataString($application.Uri.Query) -match '[?&](dbname|database|service)=') {
        throw 'DATABASE_URL must explicitly identify the application database in its path, without database or service overrides.'
    }
    # Compare by name even across different addresses to reject alternate aliases for the same database.
    if ($target.Name -ieq $application.Name) {
        throw 'The restore target matches the current application database name.'
    }

    $credentials = $target.Uri.UserInfo -split ':', 2
    if ($credentials.Count -ne 2 -or -not $credentials[0] -or -not $credentials[1]) {
        throw 'The restore target URL must contain the dedicated restore login and its password.'
    }

    if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) {
        throw 'The backup archive file does not exist.'
    }
    $archive = Get-Item -LiteralPath $BackupFile
    if ($archive.Length -le 0) { throw 'The backup archive file is empty.' }

    $restoreTool = Resolve-PgTool -Name 'pg_restore' -ExplicitPath $PgRestorePath
    $inventory = Invoke-DatabaseTool $restoreTool @('--list', $archive.FullName)
    if ($inventory.Code -ne 0 -or -not ($inventory.Output -match '^\s*\d+;\s+\d+\s+\d+\s+\S')) {
        throw 'Archive inventory was unreadable or empty. Use a trusted pg_dump custom or tar archive and a compatible pg_restore.'
    }

    if (-not $PsqlPath) {
        $sibling = Join-Path (Split-Path -Parent $restoreTool) 'psql.exe'
        if (Test-Path -LiteralPath $sibling -PathType Leaf) { $PsqlPath = $sibling }
    }
    $psql = Resolve-PgTool -Name 'psql' -ExplicitPath $PsqlPath
    $databaseEnv = @{
        PGHOST = $target.Uri.DnsSafeHost
        PGPORT = if ($target.Uri.Port -gt 0) { [string]$target.Uri.Port } else { '5432' }
        PGUSER = [Uri]::UnescapeDataString($credentials[0])
        PGPASSWORD = [Uri]::UnescapeDataString($credentials[1])
        PGDATABASE = $target.Name
        PGCONNECT_TIMEOUT = '10'
        PGHOSTADDR = $null
        PGSERVICE = $null
        PGSERVICEFILE = $null
        PGOPTIONS = $null
    }
    foreach ($name in $databaseEnv.Keys) {
        $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $databaseEnv[$name], 'Process')
    }

    $emptyDatabaseCheck = @"
SELECT CASE WHEN current_database() = '$($target.Name)'
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname NOT IN ('public', 'information_schema') AND nspname !~ '^pg_')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_extension WHERE extname <> 'plpgsql')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_largeobject_metadata)
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid())
THEN 'empty' ELSE 'occupied' END
"@
    $result = Invoke-DatabaseTool $psql @('--no-psqlrc', '--no-password', '--tuples-only', '--no-align',
        '--set', 'ON_ERROR_STOP=1', '--dbname', $target.Name, '--command', $emptyDatabaseCheck)
    if ($result.Code -ne 0 -or ($result.Output -join '').Trim() -ne 'empty') {
        throw 'The staging database could not be verified as empty. Verify connectivity and provision a fresh staging database.'
    }

    $restore = Invoke-DatabaseTool $restoreTool @('--no-password', '--single-transaction', '--exit-on-error',
        '--no-owner', '--no-privileges', '--dbname', $target.Name, $archive.FullName)
    if ($restore.Code -ne 0) {
        throw "pg_restore failed with exit code $($restore.Code). The restore transaction was rolled back."
    }
    Write-Info 'Restore completed in the staging database. Verify its integrity before changing the application connection.'
    $exitCode = 0
}
catch {
    Write-Err ("restore.ps1: " + $_.Exception.Message)
}
finally {
    foreach ($name in $previousEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], 'Process')
    }
}
exit $exitCode
