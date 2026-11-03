import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const p = spawn(
  resolve(root, ".venv/Scripts/python.exe"),
  ["-u", resolve(root, "video/scripts/demo.py"), process.argv[2] ?? "serve"],
  { cwd: root, stdio: "inherit", windowsHide: true },
);
p.on("exit", (code) => process.exit(code ?? 1));
process.on("SIGINT", () => p.kill());
