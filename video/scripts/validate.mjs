import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
const ff = "node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe";
const probe = ff.replace("ffmpeg", "ffprobe");
const path = process.argv[2] ?? "out/ai-restaurant-booker-demo.mp4";
execFileSync(process.execPath, ["scripts/captions.mjs", "--check"], {
  stdio: "inherit",
  windowsHide: true,
});
assert(existsSync(path), "No rendered MP4 exists");
const meta = JSON.parse(
  execFileSync(
    probe,
    ["-v", "error", "-show_streams", "-show_format", "-of", "json", path],
    { encoding: "utf8", windowsHide: true },
  ),
);
const v = meta.streams.find((s) => s.codec_type === "video");
const a = meta.streams.find((s) => s.codec_type === "audio");
assert.equal(v.width, 1920);
assert.equal(v.height, 1080);
assert.equal(v.codec_name, "h264");
assert.equal(v.r_frame_rate, "30/1");
assert.equal(Number(v.nb_frames), 5850);
assert(Math.abs(Number(meta.format.duration) - 195) < 0.1);
assert.equal(
  a?.codec_name,
  "aac",
  "The preview must include the fitted narration",
);
execFileSync(
  ff,
  [
    "-v",
    "error",
    "-i",
    path,
    "-c:v",
    "rawvideo",
    "-c:a",
    "pcm_s16le",
    "-f",
    "null",
    "-",
  ],
  {
    stdio: "pipe",
    windowsHide: true,
  },
);
const manifest = JSON.parse(readFileSync("public/assets.json", "utf8"));
const required = [
  "opening",
  "selection",
  "configuration",
  "outcome",
  "history",
  "history-filtered",
  "graph-before",
  "graph-after",
  "graph-return",
  "offer",
  "policy",
  "tool",
  "replay",
  "confirmation",
  "analytics",
  "playground",
  "closing",
];
const missing = required.filter(
  (id) =>
    !manifest.clips[id] || !existsSync("public/" + manifest.clips[id].src),
);
const narration = JSON.parse(readFileSync("src/timeline.json", "utf8"));
const audioTiming = narration.map((scene, i) => {
  const file = manifest.audio[String(i + 1)];
  assert(file && existsSync("public/" + file), `Missing narration ${i + 1}`);
  const seconds = Number(
    execFileSync(
      probe,
      [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        "public/" + file,
      ],
      { encoding: "utf8", windowsHide: true },
    ),
  );
  const start = scene.start + (scene.audioOffset ?? 0) + 1 / 3;
  assert(
    start + seconds < scene.start + scene.duration,
    `Narration ${i + 1} overruns its scene`,
  );
  if (i > 0) {
    const previous = narration[i - 1];
    const previousEnd =
      previous.start +
      (previous.audioOffset ?? 0) +
      1 / 3 +
      Number(
        execFileSync(
          probe,
          [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            "public/" + manifest.audio[String(i)],
          ],
          { encoding: "utf8", windowsHide: true },
        ),
      );
    assert(start >= previousEnd, `Narration ${i} overlaps narration ${i + 1}`);
  }
  return {
    scene: i + 1,
    startSeconds: start,
    durationSeconds: seconds,
    endSeconds: start + seconds,
  };
});
const sourceVideos = required.map((id) => {
  const clip = manifest.clips[id];
  assert(clip?.kind === "video", `${id} must have actual video footage`);
  const sourceMeta = JSON.parse(
    execFileSync(
      probe,
      [
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        "public/" + clip.src,
      ],
      { encoding: "utf8", windowsHide: true },
    ),
  );
  const stream = sourceMeta.streams.find((s) => s.codec_type === "video");
  assert.equal(stream.width, 1920);
  assert.equal(stream.height, 1080);
  assert.equal(stream.r_frame_rate, "30/1");
  return {
    id,
    seconds: Number(sourceMeta.format.duration),
    width: stream.width,
    height: stream.height,
    fps: stream.r_frame_rate,
  };
});
assert(
  existsSync("public/review/playground.png"),
  "Missing actual result hold image",
);
const report = {
  path,
  width: v.width,
  height: v.height,
  fps: v.r_frame_rate,
  frames: Number(v.nb_frames),
  seconds: Number(meta.format.duration),
  videoCodec: v.codec_name,
  audioCodec: a?.codec_name ?? null,
  decode: "pass",
  missingFootage: missing,
  sourceVideos,
  audioTiming,
  playgroundResult:
    "Five-second actual Electron screenshot hold; source run is video",
  narration:
    "Offline Windows TTS, provisional and replaceable; no real restaurant audio",
  music: "None",
  graphIllustration: "Explicitly labeled; not historical activity",
  subtitles: {
    language: "en",
    cues: JSON.parse(readFileSync("public/captions.en.json", "utf8")).cues
      .length,
    burnedIn: true,
    srt: "out/ai-restaurant-booker-demo.en.srt",
    webVtt: "out/ai-restaurant-booker-demo.en.vtt",
    alignment:
      "Source TTS word events, exact source PCM match, event-clock conversion and actual narration tempo",
  },
  callOpening:
    "39–46s: explicitly illustrative call initiation; original simulation-start dialog omitted; no real call claimed",
};
mkdirSync("out", { recursive: true });
writeFileSync("out/validation.json", JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
assert.equal(missing.length, 0, "Missing footage: preview is incomplete");
