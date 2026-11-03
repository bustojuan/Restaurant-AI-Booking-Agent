// Render the actual vector SVGs and measure text in Chromium. No app is started.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require("../../frontend/node_modules/@playwright/test");
const dir = dirname(fileURLToPath(import.meta.url));
const root = resolve(dir, "../..");
if (
  process.env.ARCHITECTURE_BROWSER &&
  !existsSync(process.env.ARCHITECTURE_BROWSER)
) {
  throw Error(
    "ARCHITECTURE_BROWSER does not point to an existing browser executable.",
  );
}
const choices = [
  process.env.ARCHITECTURE_BROWSER,
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  resolve(
    root,
    "video/node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe",
  ),
  chromium.executablePath(),
];
const executablePath = choices.find((p) => p && existsSync(p));
if (!executablePath)
  throw Error(
    "Set ARCHITECTURE_BROWSER or install an Edge/Chromium browser for PNG export. SVG generation itself has no dependency.",
  );
const browser = await chromium.launch({ executablePath, headless: true });
const results = [];
try {
  const page = await browser.newPage({
    viewport: { width: 1920, height: 840 },
    deviceScaleFactor: 1,
  });
  for (const name of ["system-architecture", "agent-workflow"]) {
    const svg = readFileSync(resolve(dir, `${name}.svg`), "utf8");
    await page.setViewportSize({ width: 1920, height: 840 });
    await page.setContent(
      `<html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fcfdff;overflow:hidden}svg{display:block;width:100%;height:auto}</style></head><body>${svg}</body></html>`,
    );
    await page.evaluate(() => document.fonts.ready);
    const bounds = await page.evaluate(() =>
      [...document.querySelectorAll("svg text")].flatMap((t) => {
        const b = t.getBBox(),
          limit = Number(t.dataset.maxWidth || Infinity),
          width = t.getComputedTextLength();
        return width > limit + 1 ||
          b.x < 0 ||
          b.x + b.width > 1920 ||
          b.y < 0 ||
          b.y + b.height > 840
          ? [
              {
                text: t.textContent,
                width,
                limit,
                box: { x: b.x, y: b.y, width: b.width, height: b.height },
              },
            ]
          : [];
      }),
    );
    const layout = await page.evaluate(() => {
      const texts = [...document.querySelectorAll("svg text")].map((t) => ({
        text: t.textContent,
        box: t.getBBox(),
        font: Number(t.getAttribute("font-size")),
      }));
      const overlaps = [];
      for (let i = 0; i < texts.length; i++)
        for (let j = i + 1; j < texts.length; j++) {
          const a = texts[i].box,
            b = texts[j].box;
          if (
            Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) > 2 &&
            Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) > 2
          )
            overlaps.push([texts[i].text, texts[j].text]);
        }
      const cardBounds = [...document.querySelectorAll("g[data-card]")].flatMap(
        (card) => {
          const { x, y, width, height } = card.dataset;
          return [...card.querySelectorAll("text")].flatMap((t) => {
            const b = t.getBBox();
            return b.x < Number(x) + 8 ||
              b.x + b.width > Number(x) + Number(width) - 8 ||
              b.y < Number(y) + 3 ||
              b.y + b.height > Number(y) + Number(height) - 3
              ? [{ card: card.dataset.card, text: t.textContent }]
              : [];
          });
        },
      );
      const segments = [
        ...document.querySelectorAll("path[data-connector]"),
      ].flatMap((p, id) => {
        const numbers = p
            .getAttribute("d")
            .match(/-?\d+(?:\.\d+)?/g)
            .map(Number),
          points = [];
        for (let i = 0; i < numbers.length; i += 2)
          points.push([numbers[i], numbers[i + 1]]);
        return points.slice(1).map((end, i) => ({ id, start: points[i], end }));
      });
      const crossings = [];
      for (const a of segments)
        for (const b of segments) {
          if (a.id >= b.id) continue;
          const horizontal = a.start[1] === a.end[1] ? a : b;
          const vertical = horizontal === a ? b : a;
          if (
            horizontal.start[1] !== horizontal.end[1] ||
            vertical.start[0] !== vertical.end[0]
          )
            continue;
          const x = vertical.start[0],
            y = horizontal.start[1];
          if (
            x > Math.min(horizontal.start[0], horizontal.end[0]) &&
            x < Math.max(horizontal.start[0], horizontal.end[0]) &&
            y > Math.min(vertical.start[1], vertical.end[1]) &&
            y < Math.max(vertical.start[1], vertical.end[1])
          )
            crossings.push({ connectors: [a.id, b.id], x, y });
        }
      return {
        textOverlaps: overlaps,
        cardBounds,
        connectorCrossings: crossings,
        minFontSize: Math.min(...texts.map((t) => t.font)),
      };
    });
    await page.screenshot({ path: resolve(dir, `${name}.png`) });
    const previews = [];
    for (const width of [960, 800]) {
      const height = (width * 840) / 1920;
      await page.setViewportSize({ width, height });
      const output = `${name}-${width}.png`;
      await page.screenshot({ path: resolve(dir, output) });
      previews.push({
        width,
        height,
        path: output,
        minRenderedFontSize: (layout.minFontSize * width) / 1920,
      });
    }
    results.push({
      name,
      width: 1920,
      height: 840,
      textBounds: bounds,
      ...layout,
      previews,
      svgContainsRaster: svg.includes("<image"),
      renderer: "Installed Chromium (headless), actual SVG at 1×",
    });
    console.log(
      `${name}: 1920 / 960 / 800px rendered; ${bounds.length} width issues; ${layout.textOverlaps.length} text overlaps; ${layout.cardBounds.length} card bounds; ${layout.connectorCrossings.length} connector crossings`,
    );
  }
  writeFileSync(
    resolve(dir, "render-check.json"),
    JSON.stringify(
      {
        diagrams: results,
        visualReview:
          "PNG generation and text geometry are automatic; visual inspection is a separate step",
      },
      null,
      2,
    ) + "\n",
  );
  if (
    results.some(
      (r) =>
        r.textBounds.length ||
        r.textOverlaps.length ||
        r.cardBounds.length ||
        r.connectorCrossings.length,
    )
  )
    process.exitCode = 1;
} finally {
  await browser.close();
}
