import { execFileSync } from "node:child_process";
execFileSync(
  "powershell",
  [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "scripts/narration.ps1",
  ],
  { stdio: "inherit", windowsHide: true },
);
execFileSync(process.execPath, ["scripts/audio.mjs"], {
  stdio: "inherit",
  windowsHide: true,
});
execFileSync(process.execPath, ["scripts/captions.mjs"], {
  stdio: "inherit",
  windowsHide: true,
});
