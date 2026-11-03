import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
const ff = "node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe";
const probe = "node_modules/@remotion/compositor-win32-x64-msvc/ffprobe.exe";
const scenes = JSON.parse(readFileSync("src/timeline.json", "utf8"));
const assets = JSON.parse(
  readFileSync("public/assets.json", "utf8").replace(/^\uFEFF/, ""),
);
const report = [];
for (let i = 0; i < scenes.length; i++) {
  const source = `public/audio/scene-${i + 1}.wav`;
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
        source,
      ],
      { encoding: "utf8", windowsHide: true },
    ),
  );
  const tempo = Math.max(
    1.06,
    seconds / (scenes[i].duration - (scenes[i].audioOffset ?? 0) - 1.0),
  );
  const output = `audio/narration-${i + 1}.wav`;
  execFileSync(
    ff,
    [
      "-y",
      "-i",
      source,
      "-af",
      `atempo=${tempo}`,
      "-ar",
      "48000",
      `public/${output}`,
    ],
    { stdio: "ignore", windowsHide: true },
  );
  assets.audio[String(i + 1)] = output;
  report.push({
    scene: i + 1,
    rawSeconds: seconds,
    tempo,
    source: "offline Microsoft David Desktop, provisional",
    blockSeconds: scenes[i].duration,
  });
}
writeFileSync("public/assets.json", JSON.stringify(assets, null, 2));
writeFileSync("public/audio/timing.json", JSON.stringify(report, null, 2));
console.log("Seven replaceable, duration-fitted offline narration tracks.");
