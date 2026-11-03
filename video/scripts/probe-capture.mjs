import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const require = createRequire(import.meta.url),
  {
    _electron: electron,
  } = require("../../frontend/node_modules/@playwright/test");
const root = resolve(".."),
  cfg = JSON.parse(readFileSync("private/demo/owned.json", "utf8"));
const env = {
  ...process.env,
  BARIA_BACKEND_URL: "http://127.0.0.1:18011",
  LOCAL_API_TOKEN: cfg.token,
  ADMIN_API_TOKEN: cfg.admin,
  BARIA_USER_DATA: resolve("private/demo/electron-profile"),
  BARIA_BACKEND_ENV: resolve("private/demo/unused"),
  BARIA_ADMIN_ONLY: "0",
};
delete env.ELECTRON_RUN_AS_NODE;
const app = await electron.launch({
  args: [".", "--force-device-scale-factor=1"],
  cwd: resolve(root, "frontend"),
  env,
});
const page = await app.firstWindow();
await app.evaluate(({ BrowserWindow }) => {
  for (const w of BrowserWindow.getAllWindows()) {
    w.setContentSize(1920, 1080);
    w.show();
  }
});
try {
  await page
    .getByRole("button", { name: "Advanced filters", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Restaurant catalog" })
    .selectOption("simulated");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "List", exact: true }).click();
  await page.waitForTimeout(1500);
  for (const path of [
    "/api/health",
    "/api/restaurants?region=Madrid&catalog=simulated&limit=40",
    "/api/restaurants?region=Madrid&catalog=simulated&limit=40&offset=0&favorites_only=false",
  ]) {
    const reply = await page.evaluate(
      (path) => window.desktop.request({ method: "GET", path }),
      path,
    );
    console.log(path, {
      status: reply.status,
      total: reply.data?.total,
      error: reply.data?.error,
    });
  }
  console.log(
    "UI cards:",
    await page.locator('[data-testid^="restaurant-"]').count(),
  );
  await page.screenshot({ path: "public/review/bridge-probe.png" });
} finally {
  await app.close();
}
