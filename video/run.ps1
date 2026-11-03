param([ValidateSet('studio','preview','check','prepare','start','capture','narration','captions','render','validate','review','stills','restore','reset')][string]$Command='studio')
$ErrorActionPreference='Stop'
$projectPath=Split-Path -Parent $PSScriptRoot
$portableVideoNode=Join-Path $projectPath '.tools/node-v24.22.2-win-x64'
if (Test-Path -LiteralPath (Join-Path $portableVideoNode 'node.exe')) {$env:Path=$portableVideoNode+';'+$env:Path}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {throw 'Node.js 24 or the existing portable Node installation is required.'}
$commands=@{prepare='demo:prepare';start='demo:start';restore='demo:restore';reset='demo:reset'}
$targetCommand=if ($commands.ContainsKey($Command)) {$commands[$Command]} else {$Command}
Push-Location $PSScriptRoot
try {& npm.cmd run $targetCommand; if ($LASTEXITCODE -ne 0) {throw "Video command failed: $Command"}} finally {Pop-Location}
