. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Python
Push-Location (Join-Path $repoRoot 'backend')
try { & $pythonPath -m scripts.initialize_release; Check-Exit 'Database initialization' } finally { Pop-Location }
