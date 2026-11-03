$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$scenes=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot '../src/timeline.json') | ConvertFrom-Json
$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer
$english=$synth.GetInstalledVoices() | Where-Object {$_.VoiceInfo.Culture.Name -like 'en-*'} | Select-Object -First 1
if (-not $english) {throw 'No offline English Windows voice installed. Add WAV tracks or install an English Windows voice.'}
$synth.SelectVoice($english.VoiceInfo.Name)
$synth.Rate=0
$dir=Join-Path $PSScriptRoot '../public/audio'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$manifest=Get-Content -Raw (Join-Path $PSScriptRoot '../public/assets.json') | ConvertFrom-Json
$tracks=@{}
for ($i=0;$i -lt $scenes.Count;$i++) {
  $file=Join-Path $dir "scene-$($i+1).wav"
  $synth.SetOutputToWaveFile($file)
  $synth.Speak($scenes[$i].narration)
  $tracks["$($i+1)"]="audio/scene-$($i+1).wav"
}
$synth.Dispose()
$manifest.audio=$tracks
[IO.File]::WriteAllText((Join-Path $PSScriptRoot '../public/assets.json'),($manifest | ConvertTo-Json -Depth 10),(New-Object System.Text.UTF8Encoding $false))
Write-Output "Offline provisional narration: $($english.VoiceInfo.Name). No API call, no cloning."
