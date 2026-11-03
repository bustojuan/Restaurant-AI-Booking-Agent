import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const load = (path) =>
  JSON.parse(readFileSync(path, "utf8").replace(/^\uFEFF/, ""));
const hash = (path) =>
  createHash("sha256").update(readFileSync(path)).digest("hex");
const normalize = (text) => text.replace(/\s+/g, " ").trim();
const fps = 30;
const captionPath = "public/captions.en.json";
const scenes = load("src/timeline.json");
const assets = load("public/assets.json");
const timing = load("public/audio/timing.json");
const stamps = (frames, separator = ",") => {
  const ms = Math.round((frames / fps) * 1000);
  return `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}${separator}${String(ms % 1000).padStart(3, "0")}`;
};
function linesFor(text) {
  if (text.length <= 46) return [text];
  const spaces = [...text.matchAll(/ /g)].map((m) => m.index);
  const split = spaces.reduce(
    (best, pos) =>
      Math.max(pos, text.length - pos - 1) <
      Math.max(best, text.length - best - 1)
        ? pos
        : best,
    spaces[0],
  );
  const lines = [text.slice(0, split), text.slice(split + 1)];
  assert(
    lines.every((line) => line.length <= 46),
    `Caption too wide: ${text}`,
  );
  return lines;
}

if (!process.argv.includes("--check")) {
  execFileSync(
    "powershell",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      "scripts/caption-boundaries.ps1",
    ],
    { stdio: "inherit", windowsHide: true },
  );
  const alignment = load("public/audio/word-boundaries.json");
  const cues = [];
  for (let sceneIndex = 0; sceneIndex < scenes.length; sceneIndex++) {
    const scene = scenes[sceneIndex];
    const words = alignment.scenes[sceneIndex].words;
    const tempo = timing[sceneIndex].tempo;
    const audioStart = (scene.start + (scene.audioOffset ?? 0)) * fps + 10;
    const at = (i) =>
      Math.round(audioStart + (words[i].StartSeconds / tempo) * fps);
    let first = 0;
    const flush = (last) => {
      const nextChar =
        words[last + 1]?.CharacterPosition ?? scene.narration.length;
      const text = normalize(
        scene.narration.slice(words[first].CharacterPosition, nextChar),
      );
      const startFrame = at(first);
      const endFrame =
        last + 1 < words.length
          ? at(last + 1)
          : Math.round(
              audioStart + (timing[sceneIndex].rawSeconds / tempo) * fps,
            );
      cues.push({
        scene: sceneIndex + 1,
        text,
        startMs: (startFrame * 1000) / fps,
        endMs: (endFrame * 1000) / fps,
        timestampMs: null,
        confidence: null,
        startFrame,
        endFrame,
        lines: linesFor(text),
      });
      first = last + 1;
    };
    for (let i = 0; i < words.length; i++) {
      const nextChar =
        words[i + 1]?.CharacterPosition ?? scene.narration.length;
      const candidate = normalize(
        scene.narration.slice(words[first].CharacterPosition, nextChar),
      );
      if (
        i > first &&
        (candidate.length > 78 ||
          i - first >= 12 ||
          at(i) - at(first) > 4.5 * fps)
      )
        flush(i - 1);
      const current = scene.narration
        .slice(words[first].CharacterPosition, nextChar)
        .trim();
      if (i === words.length - 1 || (/[.!?]$/.test(current) && i - first >= 3))
        flush(i);
    }
  }
  const report = {
    language: "en",
    fps,
    method: alignment.method,
    timelineSha256: hash("src/timeline.json"),
    audioSha256: scenes.map((_, i) =>
      hash(`public/${assets.audio[String(i + 1)]}`),
    ),
    cues,
  };
  writeFileSync(captionPath, JSON.stringify(report, null, 2) + "\n");
}

const captions = load(captionPath);
assert.equal(
  captions.timelineSha256,
  hash("src/timeline.json"),
  "Narration changed: regenerate captions",
);
assert.deepEqual(
  captions.audioSha256,
  scenes.map((_, i) => hash(`public/${assets.audio[String(i + 1)]}`)),
  "Audio changed: realign captions",
);
for (const [i, cue] of captions.cues.entries()) {
  assert.equal(
    cue.text,
    cue.lines.join(" "),
    "Caption text differs from its display lines",
  );
  assert.equal(cue.startMs, (cue.startFrame * 1000) / fps);
  assert.equal(cue.endMs, (cue.endFrame * 1000) / fps);
  assert(
    cue.startFrame >= 0 &&
      cue.endFrame > cue.startFrame &&
      cue.endFrame <= 5850,
    "Caption outside video",
  );
  assert(
    cue.lines.length <= 2 && cue.lines.every((line) => line.length <= 46),
    "Caption width invalid",
  );
  if (i)
    assert(
      cue.startFrame >= captions.cues[i - 1].endFrame,
      "Overlapping captions",
    );
}
for (let i = 0; i < scenes.length; i++) {
  const spoken = normalize(
    captions.cues
      .filter((cue) => cue.scene === i + 1)
      .flatMap((cue) => cue.lines)
      .join(" "),
  );
  assert.equal(
    spoken,
    normalize(scenes[i].narration),
    `Caption text incomplete for scene ${i + 1}`,
  );
}
mkdirSync("out", { recursive: true });
for (const [extension, separator] of [
  ["srt", ","],
  ["vtt", "."],
]) {
  const content = captions.cues
    .map(
      (cue, i) =>
        `${i + 1}\n${stamps(cue.startFrame, separator)} --> ${stamps(cue.endFrame, separator)}\n${cue.lines.join("\n")}\n`,
    )
    .join("\n");
  writeFileSync(
    `out/ai-restaurant-booker-demo.en.${extension}`,
    (extension === "vtt" ? "WEBVTT\n\n" : "") + content,
  );
}
console.log(
  `${captions.cues.length} complete English subtitle cues: exact source-audio alignment, fitted tempo, no overlaps; SRT + WebVTT exported.`,
);
