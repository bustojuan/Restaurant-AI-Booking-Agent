$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
function Assert-Python {
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run Instalar.cmd first.' }
}
function Assert-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        $portable = Get-ChildItem -LiteralPath (Join-Path $repoRoot '.tools') -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'node-v24*-win-x64' } | Select-Object -First 1
        if ($portable) { $env:Path = $portable.FullName + ';' + $env:Path }
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 24 LTS, then reopen PowerShell.' }
    $version = & node -p 'process.versions.node'
    if ($LASTEXITCODE -ne 0 -or $version -notlike '24.*') { throw 'Node.js 24 LTS is required by this release.' }
}
function Check-Exit([string]$operation) {
    if ($LASTEXITCODE -ne 0) { throw "$operation failed (exit $LASTEXITCODE)." }
}
