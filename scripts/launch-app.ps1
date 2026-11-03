. (Join-Path $PSScriptRoot 'common.ps1')
try {
    Assert-Python
    Push-Location (Join-Path $repoRoot 'backend')
    try {
        & $pythonPath -m scripts.launch_desktop
        Check-Exit 'BARIA'
    } finally { Pop-Location }
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
