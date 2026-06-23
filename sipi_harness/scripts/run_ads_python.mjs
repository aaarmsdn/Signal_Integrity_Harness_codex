import { spawnSync } from "node:child_process";
import fs from "node:fs";

const defaultAdsRoot = "C:\\Program Files\\Keysight\\ADS2026_Update2";
const adsRoot = process.env.HPEESOF_DIR || defaultAdsRoot;
const adsPython = process.env.ADS_PYTHON || `${adsRoot}\\tools\\python\\python.exe`;

const args = process.argv.slice(2);
if (!args.length) {
  console.error("Usage: node scripts/run_ads_python.mjs <script.py> [args...]");
  process.exit(2);
}

if (!fs.existsSync(adsPython)) {
  console.error(`ADS Python executable not found: ${adsPython}`);
  process.exit(2);
}

const result = spawnSync(adsPython, args, {
  stdio: "inherit",
  env: {
    ...process.env,
    HPEESOF_DIR: adsRoot
  },
  windowsHide: true
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 0);
