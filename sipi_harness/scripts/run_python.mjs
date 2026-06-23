import { spawnSync } from "node:child_process";
import fs from "node:fs";

const pythonExe = process.env.DOC_INGEST_PYTHON || process.env.PYTHON || "python";
const args = process.argv.slice(2);

if (!args.length) {
  console.error("Usage: node scripts/run_python.mjs <script.py|-m> [args...]");
  process.exit(2);
}

if (pythonExe.includes("\\") || pythonExe.includes("/") || pythonExe.endsWith(".exe")) {
  if (!fs.existsSync(pythonExe)) {
    console.error(`Python executable not found: ${pythonExe}`);
    process.exit(2);
  }
}

const result = spawnSync(pythonExe, args, {
  stdio: "inherit",
  env: process.env,
  windowsHide: true
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 0);
