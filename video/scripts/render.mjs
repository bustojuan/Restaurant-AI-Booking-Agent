import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
execFileSync(process.execPath, ["scripts/captions.mjs", "--check"], {
  stdio: "inherit",
  windowsHide: true,
});
mkdirSync("out", { recursive: true });
console.log("Bundling the recorded composition");
const serveUrl = await bundle({ entryPoint: "src/index.ts" });
console.log("Selecting RestaurantBooker: 5850 frames at 30 fps");
const composition = await selectComposition({
  serveUrl,
  id: "RestaurantBooker",
});
let last = -1;
await renderMedia({
  serveUrl,
  composition,
  codec: "h264",
  crf: 19,
  pixelFormat: "yuv420p",
  outputLocation: "out/ai-restaurant-booker-demo.mp4",
  concurrency: Number(process.env.BARIA_VIDEO_CONCURRENCY ?? 4),
  onProgress: ({ progress }) => {
    const n = Math.floor(progress * 100);
    if (n >= last + 5) {
      console.log(`Render ${n}%`);
      last = n;
    }
  },
});
console.log("Rendered out/ai-restaurant-booker-demo.mp4");
