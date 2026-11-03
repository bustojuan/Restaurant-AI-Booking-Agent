import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";

// These are extracted from the finished MP4, not composition mockups.
const ff = "node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe";
const input = "out/ai-restaurant-booker-demo.mp4";
const seconds = [
  12, 27, 35, 41, 55, 67, 91, 104, 115, 125, 135, 144, 151, 160, 170, 179, 187,
  192,
];
mkdirSync("out/review", { recursive: true });
for (const second of process.argv.includes("--metrics-only") ? [] : seconds) {
  execFileSync(
    ff,
    [
      "-v",
      "error",
      "-y",
      "-ss",
      String(second),
      "-i",
      input,
      "-frames:v",
      "1",
      `out/review/frame-${second}.png`,
    ],
    { stdio: "pipe", windowsHide: true },
  );
}
writeFileSync(
  "out/review/index.html",
  `<!doctype html><meta charset="utf-8"><title>Actual MP4 review frames</title><style>body{background:#101724;color:#dbe6ff;font:16px Segoe UI;padding:24px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}figure{margin:0}img{width:100%;border:1px solid #50617b}figcaption{padding:8px}</style><h1>Frames extracted from the rendered MP4</h1><p>Click a frame to inspect its full 1920×1080 image.</p><main>${seconds.map((s) => `<figure><a href="frame-${s}.png"><img src="frame-${s}.png"></a><figcaption>${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}</figcaption></figure>`).join("")}</main>`,
);
// The bundled FFmpeg omits blackdetect/volumedetect/tile. Decode small gray
// frames at four samples/second and PCM samples using supported core codecs.
const gray = execFileSync(
  ff,
  [
    "-v",
    "error",
    "-i",
    input,
    "-an",
    "-vf",
    "scale=160:90",
    "-r",
    "4",
    "-pix_fmt",
    "gray",
    "-c:v",
    "rawvideo",
    "-f",
    "image2pipe",
    "pipe:1",
  ],
  { windowsHide: true, maxBuffer: 32 * 1024 * 1024 },
);
const pixels = 160 * 90;
const blackSegments = [];
let consecutive = 0;
for (let i = 0; i + pixels <= gray.length; i += pixels) {
  let black = 0;
  for (let j = i; j < i + pixels; j++) if (gray[j] < 6) black++;
  if (black / pixels > 0.995) consecutive++;
  else {
    if (consecutive >= 2)
      blackSegments.push({
        start: i / pixels / 4 - consecutive / 4,
        seconds: consecutive / 4,
      });
    consecutive = 0;
  }
}
if (consecutive >= 2)
  blackSegments.push({
    start: gray.length / pixels / 4 - consecutive / 4,
    seconds: consecutive / 4,
  });
const wave = execFileSync(
  ff,
  [
    "-v",
    "error",
    "-i",
    input,
    "-vn",
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "pcm_s16le",
    "-f",
    "wav",
    "pipe:1",
  ],
  { windowsHide: true, maxBuffer: 16 * 1024 * 1024 },
);
let offset = 12;
while (
  offset + 8 < wave.length &&
  wave.toString("ascii", offset, offset + 4) !== "data"
)
  offset +=
    8 + wave.readUInt32LE(offset + 4) + (wave.readUInt32LE(offset + 4) % 2);
assert.equal(
  wave.toString("ascii", offset, offset + 4),
  "data",
  "PCM WAV data missing",
);
const pcm = wave.subarray(offset + 8);
let max = 0,
  squares = 0,
  clipped = 0;
for (let i = 0; i + 1 < pcm.length; i += 2) {
  const value = pcm.readInt16LE(i);
  max = Math.max(max, Math.abs(value));
  squares += value * value;
  if (Math.abs(value) >= 32760) clipped++;
}
const peak = 20 * Math.log10(max / 32768);
const mean = 20 * Math.log10(Math.sqrt(squares / (pcm.length / 2)) / 32768);
assert(
  Number.isFinite(peak) && Number.isFinite(mean),
  "No usable narration levels",
);
assert(peak <= 0 && mean > -45, "Unexpected narration levels");
assert.equal(
  blackSegments.length,
  0,
  "Unexpected black segment longer than half a second",
);
const report = {
  source: input,
  sha256: createHash("sha256").update(readFileSync(input)).digest("hex"),
  sampleSeconds: seconds,
  blackSegments,
  blackDetection:
    "Four gray samples/second, >99.5% pixels below 6/255, at least two consecutive samples",
  clippedPcmSamples: clipped,
  maxVolumeDb: peak,
  meanVolumeDb: mean,
  visualReview:
    "Extracted frames require human/agent visual inspection; metrics alone do not establish visual quality",
  audioReview:
    "Technical levels and scene fitting; no claim of an audible listening review",
};
writeFileSync("out/review/metrics.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
