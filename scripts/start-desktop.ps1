param([switch]$Production)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $portableNode = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.tools') -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'node-v24*-win-x64' } | Select-Object -First 1
    if (-not $portableNode) { throw 'Instala Node.js 24 LTS y vuelve a abrir la terminal.' }
    $env:Path = $portableNode.FullName + ';' + $env:Path
}
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
Push-Location (Join-Path $projectRoot 'frontend')
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' } }
    if (-not (Test-Path -LiteralPath 'node_modules/electron/dist/electron.exe')) { & node node_modules/electron/install.js; if ($LASTEXITCODE -ne 0) { throw 'No se pudo descargar Electron.' } }
    if ($Production) {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el frontend.' }
        & npm.cmd start
    } else { & npm.cmd run dev }
} finally { Pop-Location }
