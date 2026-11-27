[CmdletBinding()]
param (
    [ValidateSet('Dev', 'Build', 'Start')]
    [string]$Mode = 'Dev',

    [ValidateRange(1024, 65535)]
    [int]$Port = 3001
)

$ErrorActionPreference = 'Stop'
$appDirectory = Join-Path $PSScriptRoot '..\apps\admin-web'
$pnpmCommand = Get-Command pnpm -CommandType Application -ErrorAction Stop | Select-Object -First 1

if (-not (Test-Path -LiteralPath (Join-Path $appDirectory 'node_modules\.bin\next.cmd'))) {
    throw 'Install the admin dependencies first: pnpm --dir apps/admin-web install --frozen-lockfile'
}

Push-Location -LiteralPath $appDirectory
try {
    switch ($Mode) {
        'Build' { & $pnpmCommand.Source run build }
        'Start' { & $pnpmCommand.Source exec next start -H 127.0.0.1 -p $Port }
        default { & $pnpmCommand.Source exec next dev -H 127.0.0.1 -p $Port }
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
