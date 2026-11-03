param([switch]$Admin)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Node
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Push-Location (Join-Path $repoRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'out/main/index.js')) { throw 'Run scripts/setup.ps1 to build Electron first.' }
    if ($Admin) { & npm.cmd run start:admin } else { & npm.cmd start }
    Check-Exit 'Electron'
} finally { Pop-Location }
