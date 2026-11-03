param([switch]$Development)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $portableNode = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.tools') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'node-v24*-win-x64' } | Select-Object -First 1
    if (-not $portableNode) { throw 'Instala Node.js 24 LTS y vuelve a abrir la terminal.' }
    $env:Path = $portableNode.FullName + ';' + $env:Path
}
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Push-Location (Join-Path $projectRoot 'backend')
try {
    & '../.venv/Scripts/python.exe' -m scripts.configure_admin
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo configurar el acceso administrativo.' }
} finally { Pop-Location }
Write-Host 'El backend debe estar iniciado con la configuracion actual en el puerto 8001.'
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' } }
    if ($Development) { & npm.cmd run dev:admin }
    else {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar AI Control Center.' }
        & npm.cmd run start:admin
    }
} finally { Pop-Location }
