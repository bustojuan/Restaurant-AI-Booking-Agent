import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, execFileSync } from "node:child_process";
const require = createRequire(import.meta.url);
const {
  _electron: electron,
  expect,
} = require("../../frontend/node_modules/@playwright/test");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const dir = resolve(root, "video/private/demo");
const cfg = JSON.parse(readFileSync(resolve(dir, "owned.json"), "utf8"));
const origin = "http://127.0.0.1:18011";
const publicDir = resolve(root, "video/public");
const rawDir = resolve(root, "video/private/raw");
mkdirSync(rawDir, { recursive: true });
mkdirSync(resolve(publicDir, "footage"), { recursive: true });
mkdirSync(resolve(publicDir, "review"), { recursive: true });
const assetsPath = resolve(publicDir, "assets.json");
let assets = JSON.parse(
  readFileSync(assetsPath, "utf8").replace(/^\uFEFF/, ""),
);
if (
  assets.captureStatus === "captured" &&
  existsSync(resolve(dir, "hero.json")) &&
  JSON.parse(readFileSync(resolve(dir, "hero.json"), "utf8")).id ===
    assets.heroBookingId &&
  !process.env.BARIA_VIDEO_REFRESH
) {
  console.log(
    "Completed capture retained. Use demo:restore for a fresh coherent take, or BARIA_VIDEO_REFRESH=<clip-id> for a read-only retake.",
  );
  process.exit(0);
}
async function api(
  path,
  method = "GET",
  body,
  version,
  admin = false,
  retry = 0,
) {
  try {
    const r = await fetch(
      origin + "/api" + (admin ? "/admin/observability" : "") + path,
      {
        method,
        signal: AbortSignal.timeout(20000),
        headers: {
          Authorization: `Bearer ${admin ? cfg.admin : cfg.token}`,
          "Content-Type": "application/json",
          ...(version ? { "If-Match": String(version) } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      },
    );
    if (!r.ok)
      throw Error(
        `${method} ${path}: ${r.status} ${(await r.text()).slice(0, 400)}`,
      );
    return r.status === 204 ? null : r.json();
  } catch (error) {
    if (method === "GET" && retry < 3) {
      await new Promise((r) => setTimeout(r, 250));
      return api(path, method, body, version, admin, retry + 1);
    }
    throw error;
  }
}
let server;
try {
  await api("/workspace");
} catch {
  server = spawn(
    resolve(root, ".venv/Scripts/python.exe"),
    ["-u", resolve(root, "video/scripts/demo.py"), "serve"],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
  );
  server.stderr.on("data", () => {});
  for (let i = 0; i < 120; i++) {
    try {
      await api("/workspace");
      break;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
    if (i === 119) throw Error("Demo server not ready");
  }
}
let hero = existsSync(resolve(dir, "hero.json"))
  ? JSON.parse(readFileSync(resolve(dir, "hero.json"), "utf8"))
  : null;
if (!hero) {
  const requested = new Date(cfg.anchor + "T12:00:00Z");
  requested.setUTCDate(requested.getUTCDate() + 14);
  hero = await api("/bookings", "POST", {
    configuration: {
      customer_name: "Demo Guest",
      contact_phone: "000000000",
      requested_date: requested.toISOString().slice(0, 10),
      preferred_time: "21:00:00",
      adults: 4,
      flexibility_minutes: 30,
      table_type: "terrace",
      table_type_mandatory: false,
      dietary_requirements: [
        { kind: "celiac", code: "gluten", mandatory: true },
      ],
      notes: "Quiet area if available.",
    },
    restaurant_ids: [],
  });
  writeFileSync(resolve(dir, "hero.json"), JSON.stringify(hero, null, 2));
}
hero = await api(`/bookings/${hero.id}`);
if (assets.heroBookingId && assets.heroBookingId !== hero.id) assets.clips = {};
assets.heroBookingId = hero.id;
if (hero.status === "DRAFT") {
  const w = await api("/workspace");
  await api("/workspace", "PUT", { active_draft_id: hero.id }, w.version);
}
const adminOnly = hero.status !== "DRAFT" && !!assets.clips.outcome;
const env = {
  ...process.env,
  BARIA_BACKEND_URL: origin,
  LOCAL_API_TOKEN: cfg.token,
  ADMIN_API_TOKEN: cfg.admin,
  BARIA_BACKEND_ENV: resolve(dir, "unused-no-personal-env"),
  BARIA_USER_DATA: resolve(dir, "electron-profile"),
  BARIA_ADMIN_ONLY: adminOnly ? "1" : "0",
};
delete env.ELECTRON_RUN_AS_NODE;
const ffmpeg = resolve(
  root,
  "video/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe",
);
console.log("Launching isolated Electron capture (live Chromium recorder)");
const app = await electron.launch({
  args: [".", "--force-device-scale-factor=1"],
  cwd: resolve(root, "frontend"),
  env,
  timeout: 90000,
});
console.log("Electron connected");
const clips = [];
let main, admin;
async function resize(page) {
  await app.evaluate(({ BrowserWindow }) => {
    for (const w of BrowserWindow.getAllWindows()) {
      w.setContentSize(1920, 1080);
      w.show();
    }
  });
}
async function take(page, id, seconds, action = async () => {}) {
  if (
    assets.clips[id] &&
    !process.env.BARIA_VIDEO_REFRESH?.split(",").includes(id)
  ) {
    console.log(`Reuse verified clip ${id}`);
    await action();
    return;
  }
  const file = resolve(publicDir, "footage", id + ".mp4");
  const session = await page.context().newCDPSession(page);
  let latest = null;
  session.on("Page.screencastFrame", async (e) => {
    latest = Buffer.from(e.data, "base64");
    await session
      .send("Page.screencastFrameAck", { sessionId: e.sessionId })
      .catch(() => {});
  });
  await session.send("Page.startScreencast", {
    format: "jpeg",
    quality: 92,
    maxWidth: 1920,
    maxHeight: 1080,
    everyNthFrame: 1,
  });
  for (let i = 0; !latest && i < 100; i++)
    await new Promise((r) => setTimeout(r, 50));
  if (!latest)
    throw Error("No frames from actual Electron Chromium screencast");
  const recorder = spawn(
    ffmpeg,
    [
      "-y",
      "-f",
      "image2pipe",
      "-c:v",
      "mjpeg",
      "-framerate",
      "30",
      "-i",
      "pipe:0",
      "-an",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "19",
      "-pix_fmt",
      "yuv420p",
      file,
    ],
    { stdio: ["pipe", "ignore", "pipe"], windowsHide: true },
  );
  let log = "";
  recorder.stderr.on("data", (b) => {
    log += b.toString();
  });
  const start = Date.now();
  let frameCount = 0;
  const tick = () => {
    const wanted = Math.floor(((Date.now() - start) * 30) / 1000);
    while (latest && frameCount < wanted) {
      recorder.stdin.write(latest);
      frameCount++;
    }
  };
  const timer = setInterval(tick, 16);
  console.log(`Capture ${id} (live Chromium frames)`);
  try {
    await action();
    await page.waitForTimeout(
      Math.max(500, seconds * 1000 - (Date.now() - start)),
    );
  } finally {
    clearInterval(timer);
    tick();
    recorder.stdin.end();
    await new Promise((ok, fail) =>
      recorder.once("exit", (c) =>
        c === 0
          ? ok()
          : fail(Error("Screencast encoding failed " + log.slice(-500))),
      ),
    );
    await session.send("Page.stopScreencast");
    await session.detach();
  }
  const shot = { id, page, start, end: Date.now(), nativeFile: file };
  clips.push(shot);
  await page.screenshot({ path: resolve(publicDir, "review", `${id}.png`) });
}
async function nav(name) {
  await admin
    .locator(".ac-sidebar nav")
    .getByRole("button", { name, exact: name !== "Calls" })
    .click();
}
async function calls(bookingId = hero.id) {
  await nav("Calls");
  await admin.getByRole("textbox", { name: "Search calls" }).fill(bookingId);
  await admin.waitForTimeout(650);
}
async function detail(id, bookingId = hero.id) {
  await calls(bookingId);
  await admin.getByTestId(`call-row-${id}`).click();
  await expect(admin.getByTestId("attempt-summary")).toBeVisible();
}
async function full() {
  await admin
    .getByRole("combobox", { name: "Execution scope" })
    .selectOption("execution");
  await admin.waitForTimeout(500);
}
async function event(e) {
  await admin.getByRole("button", { name: /^All events/ }).click();
  await admin
    .getByRole("button", { name: `Event ${e.id} ${e.kind}`, exact: true })
    .click();
}
async function closeInspector() {
  const b = admin.getByRole("button", { name: "Close inspector" });
  if (await b.count()) await b.click();
}
let failure;
try {
  main = await app.firstWindow();
  console.log("First window connected");
  main.setDefaultTimeout(18000);
  await resize(main);
  console.log("Window resized");
  if (!adminOnly)
    await expect(
      main.getByRole("button", { name: "Start AI Booking", exact: true }),
    ).toBeVisible();
  if (hero.status === "DRAFT") {
    await main.getByTestId("map").waitFor({ timeout: 45000 });
    await main.waitForTimeout(7000);
    await take(main, "opening", 20, async () => {
      await main.getByRole("button", { name: "Navarra", exact: true }).click();
      await main.waitForTimeout(2000);
      await main.getByRole("button", { name: "Madrid", exact: true }).click();
      await main.waitForTimeout(2000);
      await main.getByRole("button", { name: "2D", exact: true }).click();
      await main.getByRole("button", { name: "3D", exact: true }).click();
    });
    await main
      .getByRole("button", { name: "Advanced filters", exact: true })
      .click();
    await main
      .getByRole("combobox", { name: "Restaurant catalog" })
      .selectOption("simulated");
    await main.keyboard.press("Escape");
    await main.getByRole("button", { name: "List", exact: true }).click();
    await expect(main.getByTestId("restaurant-madrid-2")).toBeVisible({
      timeout: 45000,
    });
    await take(main, "selection", 11, async () => {
      const favorite = main
        .getByTestId("restaurant-madrid-1")
        .getByRole("button", { name: /Save favorite/ });
      if (await favorite.count()) await favorite.click();
      for (const id of ["madrid-2", "madrid-3", "madrid-1"]) {
        if (await main.getByTestId(`queue-${id}`).count()) continue;
        await main
          .getByTestId(`restaurant-${id}`)
          .getByRole("button", { name: "Add", exact: true })
          .click();
      }
      const source = main.getByTestId("queue-madrid-1").locator(".drag-handle");
      const target = main.getByTestId("queue-madrid-2");
      await source.scrollIntoViewIfNeeded();
      const a = await source.boundingBox(),
        b = await target.boundingBox();
      if (!a || !b) throw Error("Missing drag bounds");
      await main.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
      await main.mouse.down();
      await main.mouse.move(a.x + 15, a.y + 8, { steps: 6 });
      await main.mouse.move(b.x + 30, b.y + 8, { steps: 30 });
      await main.waitForTimeout(350);
      await main.mouse.up();
      await expect(
        main.getByTestId("queue-madrid-1").locator(".priority"),
      ).toHaveText("1");
    });
    await take(main, "configuration", 8, async () => {
      await main.getByLabel("Booking time", { exact: true }).focus();
    });
    await take(main, "start", 3, async () => {
      await main
        .getByRole("button", { name: "Start AI Booking", exact: true })
        .click();
      await expect(
        main.getByRole("button", { name: "Start simulation", exact: true }),
      ).toBeEnabled();
    });
    await main
      .getByRole("button", { name: "Start simulation", exact: true })
      .click();
    await take(main, "outcome", 14, async () => {
      await expect
        .poll(async () => (await api(`/bookings/${hero.id}`)).status, {
          timeout: 60000,
        })
        .toBe("CONFIRMED");
    });
  }
  if (hero.status !== "DRAFT" && !assets.clips.outcome) {
    await main.getByRole("button", { name: /^Bookings/ }).click();
    await main.getByRole("tab", { name: /History/ }).click();
    await main.locator(".history-preview").first().click();
    await expect(main.locator(".confirmation-card")).toBeVisible();
    await take(main, "outcome", 14);
    await main.keyboard.press("Escape");
  }
  const summary = (await api(`/bookings/${hero.id}`)).summary;
  const found = await api(
    `/calls?q=${hero.id}`,
    "GET",
    undefined,
    undefined,
    true,
  );
  const attempts = [...found.items].sort((a, b) => a.sequence - b.sequence);
  if (
    attempts.length !== 3 ||
    attempts[1].result !== "INCOMPATIBLE_OFFER" ||
    attempts[2].result !== "CONFIRMED"
  )
    throw Error("Hero continuity mismatch");
  const C = attempts[2],
    B = attempts[1];
  const eventPage = await api(
    `/events?execution_id=${C.execution_id}&limit=200`,
    "GET",
    undefined,
    undefined,
    true,
  );
  const events = eventPage.items;
  writeFileSync(
    resolve(dir, "bookmarks.json"),
    JSON.stringify({ booking: hero.id, attempts, events, summary }, null, 2),
  );
  if (adminOnly) {
    admin = main;
  } else {
    const pending = app.waitForEvent("window");
    await main
      .getByRole("button", { name: "AI Control Center", exact: true })
      .click();
    admin = await pending;
    await main.close();
  }
  admin.setDefaultTimeout(20000);
  await resize(admin);
  await expect(admin.getByTestId("admin-calls")).toBeVisible();
  await take(admin, "history", 14, async () => {
    await admin.getByRole("tab", { name: "Booking view", exact: true }).click();
    await admin.waitForTimeout(2000);
    await admin
      .getByRole("tab", { name: "Call view", exact: true })
      .last()
      .click();
  });
  await take(admin, "history-filtered", 11, async () => {
    await admin.getByRole("textbox", { name: "Search calls" }).fill(hero.id);
    await admin.waitForTimeout(1500);
    await admin.getByTestId(`call-row-${C.id}`).click();
  });
  await full();
  await admin.getByRole("button", { name: "Expand graph" }).click();
  await take(admin, "graph-before", 11, async () => {
    await admin.locator('.react-flow__node[data-id="planning"]').click();
    await admin.waitForTimeout(1200);
  });
  await take(admin, "graph-after", 10, async () => {
    await admin.locator('.react-flow__node[data-id="memory"]').click();
    await admin.waitForTimeout(2200);
  });
  await admin.getByRole("button", { name: "Restore graph" }).click();
  await closeInspector();
  const supervisors = events.filter(
    (e) =>
      e.kind === "graph.node" &&
      e.node === "supervisor" &&
      e.phase === "started",
  );
  await take(admin, "graph-return", 9, async () => {
    await event(supervisors[2]);
    await closeInspector();
  });
  await detail(B.id);
  await take(admin, "offer", 10, async () => {
    const offer = admin
      .getByRole("button", { name: /View evidence:.*[Oo]ffer/ })
      .first();
    await expect(offer).toBeVisible();
    await offer.click();
    await expect(admin.getByTestId("attempt-evidence")).toBeVisible();
  });
  await full();
  const review = events.find(
    (e) =>
      e.kind === "agent" &&
      e.node === "negotiation" &&
      e.phase === "completed" &&
      e.data?.output?.evaluation === "UNACCEPTABLE",
  );
  if (!review) throw Error("Recorded B policy agent event missing");
  await take(admin, "policy", 7, async () => {
    await event(review);
    await admin.getByRole("tab", { name: "I/O", exact: true }).click();
  });
  const wrappers = events.filter(
    (e) =>
      e.kind === "graph.node" &&
      e.node === "voice_session" &&
      e.phase === "started",
  );
  const voiceAgent = events.find(
    (e) =>
      e.kind === "agent" &&
      e.phase === "started" &&
      e.node === "voice_session" &&
      e.parent_span_id === wrappers[1].span_id,
  );
  if (!voiceAgent) throw Error("Recorded B voice invocation missing");
  const tool = events.find(
    (e) =>
      e.kind === "tool" &&
      e.tool === "persist_call_outcome" &&
      e.phase === "completed" &&
      e.parent_span_id === voiceAgent.span_id,
  );
  if (!tool) throw Error("Recorded B tool event missing");
  await take(admin, "tool", 8, async () => {
    await event(tool);
    await admin.getByRole("tab", { name: "I/O", exact: true }).click();
  });
  await take(admin, "replay", 9, async () => {
    await admin.getByRole("tab", { name: "Timing", exact: true }).click();
    await admin.waitForTimeout(1800);
    await event(wrappers[1]);
    await closeInspector();
    await admin.locator(".react-flow__controls-fitview").click();
    await admin
      .getByRole("combobox", { name: "Replay speed" })
      .selectOption("0.5");
    await admin.getByRole("button", { name: "Play history" }).click();
    await admin.waitForTimeout(500);
    await admin.locator(".react-flow__controls-fitview").click();
    await admin.waitForTimeout(2200);
    await admin.getByRole("button", { name: "Pause replay" }).click();
    await admin.getByRole("button", { name: "Next event" }).click();
    await admin.waitForTimeout(400);
    await admin.locator(".react-flow__controls-fitview").click();
  });
  await detail(C.id);
  await take(admin, "confirmation", 11, async () => {
    await admin
      .getByRole("button", { name: /View evidence:.*[Cc]onfirmation/ })
      .first()
      .click();
  });
  if (!existsSync(resolve(dir, "analytics-300.json"))) {
    const aggregate = await api(
      `/analytics?date_from=${new Date(new Date(cfg.anchor + "T12:00:00Z").getTime() - 41 * 86400000).toISOString().slice(0, 10)}&date_to=${cfg.anchor}&mode=ai_simulation`,
      "GET",
      undefined,
      undefined,
      true,
    );
    writeFileSync(
      resolve(dir, "analytics-300.json"),
      JSON.stringify(aggregate, null, 2),
    );
    if (aggregate.calls !== 300 || aggregate.bookings !== 120)
      throw Error("Analytics take requires the 300-call pre-lab stage");
  }
  if (
    process.env.BARIA_VIDEO_REFRESH?.split(",").includes("analytics") &&
    existsSync(resolve(dir, "lab.json"))
  )
    throw Error(
      "Restore baseline before refreshing the pre-lab Analytics take",
    );
  await nav("Analytics");
  await admin
    .getByRole("combobox", { name: "Analytics period" })
    .selectOption("custom");
  await admin
    .getByLabel("Analytics from", { exact: true })
    .fill(
      new Date(new Date(cfg.anchor + "T12:00:00Z").getTime() - 41 * 86400000)
        .toISOString()
        .slice(0, 10),
    );
  await admin.getByLabel("Analytics to", { exact: true }).fill(cfg.anchor);
  await admin.waitForTimeout(900);
  await take(admin, "analytics", 7);
  if (assets.clips.playground && existsSync(resolve(dir, "lab.json"))) {
    const lab = JSON.parse(readFileSync(resolve(dir, "lab.json"), "utf8"));
    await detail(lab.call_id, lab.booking_id);
  } else {
    if (existsSync(resolve(dir, "lab.json")))
      throw Error(
        "A laboratory run already exists; retain its footage or restore before a new run",
      );
    await nav("Playground");
    await admin
      .getByRole("button", { name: /First restaurant confirms/ })
      .click();
    await take(admin, "playground", 8, async () => {
      await admin
        .getByRole("button", { name: "Run simulation", exact: true })
        .click();
      await expect(
        admin.getByText("Evaluation passed", { exact: true }),
      ).toBeVisible({ timeout: 45000 });
      const labCalls = await api(
        "/calls?limit=1",
        "GET",
        undefined,
        undefined,
        true,
      );
      if (labCalls.items[0].booking_id === hero.id)
        throw Error("Lab did not create a separate booking");
      writeFileSync(
        resolve(dir, "lab.json"),
        JSON.stringify(
          {
            booking_id: labCalls.items[0].booking_id,
            call_id: labCalls.items[0].id,
          },
          null,
          2,
        ),
      );
    });
    await admin.locator(".ac-simulation-calls button").first().click();
    await expect(admin.getByTestId("call-detail")).toBeVisible();
  }
  await expect(
    admin.locator('.react-flow__node[data-id="evaluation"]'),
  ).toBeVisible();
  await admin.locator(".react-flow__controls-fitview").click();
  await admin.waitForTimeout(400);
  await take(admin, "closing", 5);
  for (const [width, height] of [
    [1440, 900],
    [1920, 1080],
  ]) {
    await app.evaluate(
      ({ BrowserWindow }, size) => {
        for (const w of BrowserWindow.getAllWindows())
          w.setContentSize(size[0], size[1]);
      },
      [width, height],
    );
    await admin.waitForTimeout(400);
    await admin.locator(".react-flow__controls-fitview").click();
    await admin.waitForTimeout(400);
    await admin.screenshot({
      path: resolve(publicDir, "review", `final-graph-${width}.png`),
    });
  }
} catch (e) {
  failure = e;
  console.error("Capture interrupted:", e.message);
  if (admin || main)
    await (admin ?? main)
      .screenshot({ path: resolve(publicDir, "review", "capture-failure.png") })
      .catch(() => {});
} finally {
  await app.close();
  const ff = resolve(
    root,
    "video/node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe",
  );
  const probe = ff.replace("ffmpeg.exe", "ffprobe.exe");
  const reportFile = resolve(publicDir, "capture-report.json");
  const savedReport = existsSync(reportFile)
    ? JSON.parse(readFileSync(reportFile, "utf8"))
    : { clips: [] };
  const previousReport =
    savedReport.hero_booking_id && savedReport.hero_booking_id !== hero.id
      ? { clips: [] }
      : savedReport;
  const captureReport = previousReport.clips.filter(
    (c) => !clips.some((n) => n.id === c.id),
  );
  for (const c of clips) {
    if (c.nativeFile) {
      const meta = JSON.parse(
        execFileSync(
          probe,
          [
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            c.nativeFile,
          ],
          { encoding: "utf8", windowsHide: true },
        ),
      );
      const v = meta.streams.find((s) => s.codec_type === "video");
      const seconds = Number(meta.format.duration);
      assets.clips[c.id] = {
        src: "footage/" + c.id + ".mp4",
        duration: Math.floor(seconds * 30),
        kind: "video",
        ...(c.id === "outcome" && seconds > 14
          ? { start: Math.floor((seconds - 14) * 30) }
          : {}),
      };
      captureReport.push({
        id: c.id,
        source:
          "actual Electron renderer / live CDP screencast, operated by Playwright",
        seconds,
        width: v.width,
        height: v.height,
        fps: v.r_frame_rate,
        booking_id: ["playground", "closing"].includes(c.id) ? null : hero.id,
      });
      continue;
    }
  }
  if (existsSync(resolve(publicDir, "review/playground.png")))
    assets.clips["playground-result"] = {
      src: "review/playground.png",
      kind: "image",
      provenance:
        "Actual Electron result screenshot; five-second editorial hold, not video footage",
    };
  assets.captureStatus = failure ? "partial" : "captured";
  writeFileSync(assetsPath, JSON.stringify(assets, null, 2));
  writeFileSync(
    resolve(publicDir, "capture-report.json"),
    JSON.stringify(
      {
        status: assets.captureStatus,
        hero_booking_id: hero.id,
        clips: captureReport,
        error: failure?.message ?? null,
      },
      null,
      2,
    ),
  );
  try {
    const workspace = await api("/workspace");
    if (workspace.active_draft_id && workspace.active_draft_id !== hero.id) {
      const blank = await api(`/bookings/${workspace.active_draft_id}`);
      if (
        blank.status === "DRAFT" &&
        blank.restaurants.length === 0 &&
        !blank.configuration.customer_name
      )
        await api(`/bookings/${blank.id}`, "DELETE", undefined, blank.version);
    }
    execFileSync(
      resolve(root, ".venv/Scripts/python.exe"),
      [resolve(root, "video/scripts/demo.py"), "snapshot"],
      { cwd: root, stdio: "inherit", windowsHide: true },
    );
  } catch (e) {
    console.error("Snapshot/blank-draft cleanup:", e.message);
  }
  if (server && server.exitCode === null) {
    try {
      execFileSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
    } catch {}
  }
}
if (failure) process.exitCode = 1;
