import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import { mkdirSync } from "node:fs";
const serveUrl = await bundle({ entryPoint: "src/index.ts" });
const composition = await selectComposition({
  serveUrl,
  id: "RestaurantBooker",
});
mkdirSync("out/composition-review", { recursive: true });
const requested = process.argv.slice(2).map(Number);
const seconds = requested.length
  ? requested
  : [
      12, 25, 35, 41, 51, 71, 79, 90, 104, 115, 125, 135, 144, 151, 160, 169,
      178, 183, 187, 192,
    ];
if (
  seconds.some(
    (second) => !Number.isFinite(second) || second < 0 || second >= 195,
  )
) {
  throw new Error("Still times must be seconds between 0 and 195.");
}
for (const second of seconds) {
  await renderStill({
    serveUrl,
    composition,
    frame: Math.round(second * composition.fps),
    imageFormat: "png",
    output: `out/composition-review/second-${second}.png`,
  });
  console.log(`Composition still at ${second}s (not an MP4 frame)`);
}
