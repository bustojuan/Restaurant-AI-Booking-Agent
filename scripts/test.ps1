param([switch]$WithVideo)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Python
Assert-Node
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Push-Location (Join-Path $repoRoot 'backend')
try {
    & $pythonPath -m compileall -q app scripts tests alembic
    Check-Exit 'Python compilation'
    & $pythonPath -m ruff check .
    Check-Exit 'Python lint'
    & $pythonPath -m ruff format --check .
    Check-Exit 'Python formatting'
    & $pythonPath -m pytest -q
    Check-Exit 'Backend tests'
} finally { Pop-Location }
Push-Location (Join-Path $repoRoot 'frontend')
try {
    & npm.cmd test
    Check-Exit 'Frontend unit tests'
    & npm.cmd run build
    Check-Exit 'TypeScript and Electron production build'
    & npm.cmd run test:e2e
    Check-Exit 'Electron end-to-end tests'
} finally { Pop-Location }
if ($WithVideo) {
    Push-Location (Join-Path $repoRoot 'video')
    try { & npm.cmd run check; Check-Exit 'Remotion TypeScript' } finally { Pop-Location }
}
