param([switch]$WithVideo)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Node
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv (https://docs.astral.sh/uv/getting-started/installation/), then reopen PowerShell.'
}
Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & uv venv --python 3.14 --no-project .venv
        Check-Exit 'Python 3.14 environment creation'
    }
    Push-Location backend
    try {
        # Copy mode supports OneDrive directories without incompatible hardlinks.
        # Install pinned versions without removing the editable backend on every rerun.
        & uv pip install --require-hashes --link-mode=copy --python $pythonPath -r requirements-dev.lock.txt
        Check-Exit 'Locked Python dependency installation'
        & uv pip install --link-mode=copy --python $pythonPath --no-deps -e .
        Check-Exit 'Backend package installation'
        & $pythonPath -m scripts.initialize_release
        Check-Exit 'Configuration and database initialization'
    } finally { Pop-Location }
    Push-Location frontend
    try {
        & npm.cmd ci
        Check-Exit 'Frontend installation'
        # Electron 45 downloads its executable lazily; provision it during installation.
        & node -e "require('electron')"
        Check-Exit 'Electron runtime download'
        & npm.cmd run build
        Check-Exit 'Frontend build'
    } finally { Pop-Location }
    if ($WithVideo) {
        Push-Location video
        try { & npm.cmd ci; Check-Exit 'Remotion installation' } finally { Pop-Location }
    }
    Write-Host 'Ready. Double-click "Iniciar BARIA.cmd" to open the application.'
} finally { Pop-Location }
