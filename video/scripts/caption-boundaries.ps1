$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies @('System.Speech', 'System.Core') -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Speech.AudioFormat;
using System.Speech.Synthesis;

public class CaptionBoundary {
    public string Text;
    public int CharacterPosition;
    public int CharacterCount;
    public double StartSeconds;
}
public class CaptionAlignment {
    public List<CaptionBoundary> Words = new List<CaptionBoundary>();
    public string PcmHash;
}
public static class CaptionAligner {
    public static string Digest(byte[] samples) {
        using (var hash = SHA256.Create()) {
            return BitConverter.ToString(hash.ComputeHash(samples)).Replace("-", "").ToLowerInvariant();
        }
    }
    public static string WavePcmHash(string path) {
        byte[] wave = File.ReadAllBytes(path);
        for (int offset = 12; offset + 8 <= wave.Length;) {
            int count = BitConverter.ToInt32(wave, offset + 4);
            if (System.Text.Encoding.ASCII.GetString(wave, offset, 4) == "data") {
                return Digest(wave.Skip(offset + 8).Take(count).ToArray());
            }
            offset += 8 + count + (count % 2);
        }
        throw new InvalidDataException("WAV PCM data not found");
    }
    public static CaptionAlignment Align(string text, string voice) {
        var result = new CaptionAlignment();
        using (var synth = new SpeechSynthesizer())
        using (var wave = new MemoryStream()) {
            synth.SelectVoice(voice);
            synth.Rate = 0;
            synth.SpeakProgress += (sender, e) => result.Words.Add(new CaptionBoundary {
                Text = e.Text, CharacterPosition = e.CharacterPosition,
                // The installed David engine reports a 16 kHz event clock
                // for the identical PCM emitted at 22.05 kHz. Convert clocks;
                // these are source events, not uniformly estimated word times.
                CharacterCount = e.CharacterCount, StartSeconds = e.AudioPosition.TotalSeconds * 16000.0 / 22050.0
            });
            // Keep PCM identical to the existing narration source format.
            synth.SetOutputToAudioStream(wave, new SpeechAudioFormatInfo(22050, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
            synth.Speak(text);
            synth.SetOutputToNull();
            result.PcmHash = Digest(wave.ToArray());
        }
        return result;
    }
}
'@
$root = Join-Path $PSScriptRoot '..'
$scenes = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'src/timeline.json') | ConvertFrom-Json
$probe = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $probe.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -eq 'Microsoft David Desktop' } | Select-Object -First 1
if (-not $voice) { throw 'The existing narration uses Microsoft David Desktop. Supply word alignment for a replacement voice rather than estimating subtitles.' }
$probe.Dispose()
$results = @()
for ($i = 0; $i -lt $scenes.Count; $i++) {
    $aligned = [CaptionAligner]::Align($scenes[$i].narration, $voice.VoiceInfo.Name)
    $source = Join-Path $root "public/audio/scene-$($i+1).wav"
    $originalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
    # Exact audio comparison makes the SAPI timestamps evidence for the existing
    # source narration. A new voice/recording needs new alignment, not these times.
    if ($aligned.PcmHash -ne [CaptionAligner]::WavePcmHash($source)) { throw "Scene $($i+1): synthesized audio differs from the original track; realign the replacement audio." }
    if ($aligned.Words.Count -eq 0) { throw "No word timestamps for scene $($i+1)" }
    $results += @{ scene = $i+1; sourceSha256 = $originalHash; words = $aligned.Words }
    Write-Output "Aligned scene $($i+1): $($aligned.Words.Count) boundaries; source PCM hash matches."
}
$report = @{ voice = $voice.VoiceInfo.Name; method = 'David SpeakProgress offsets converted from 16000 Hz event clock to 22050 Hz source PCM; exact source PCM SHA-256 match'; scenes = $results }
[IO.File]::WriteAllText((Join-Path $root 'public/audio/word-boundaries.json'), ($report | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding $false))
