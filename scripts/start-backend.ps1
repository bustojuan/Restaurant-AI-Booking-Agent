. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Python
Push-Location (Join-Path $repoRoot 'backend')
try {
    & $pythonPath -m app.migrate
    Check-Exit 'Database migration'
    & $pythonPath -m app.main
    Check-Exit 'Backend'
} finally { Pop-Location }
