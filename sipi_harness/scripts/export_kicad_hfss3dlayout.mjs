import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Export KiCad board interchange files for HFSS 3D Layout handoff.

Usage:
  node scripts/export_kicad_hfss3dlayout.mjs --board <board.kicad_pcb> --out-dir <dir> [--prefix <name>]

Outputs:
  <prefix>_odb.zip
  <prefix>_ipc2581.xml
  hfss3dlayout_export_summary.json

Notes:
  This script only exports interchange files. HFSS ports are created later from
  port-intent JSON, preferably as AEDB polygon-edge gap ports.`);
  process.exit(0);
}

const cwd = process.cwd();
const workspace = path.basename(cwd) === "sipi_harness" ? path.resolve("..") : cwd;
const kicadCli = "C:\\Program Files\\KiCad\\9.0\\bin\\kicad-cli.exe";

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const boardPath = path.resolve(workspace, argValue("--board", "outputs/kicad_microstrip_50ohm/microstrip_50ohm_fr4_1p6.kicad_pcb"));
const outDir = path.resolve(workspace, argValue("--out-dir", "outputs/hfss3dlayout_import"));
const prefix = argValue("--prefix", path.basename(boardPath, ".kicad_pcb"));
const odbPath = path.join(outDir, `${prefix}_odb.zip`);
const ipcPath = path.join(outDir, `${prefix}_ipc2581.xml`);

function run(args) {
  const result = spawnSync(kicadCli, args, {
    cwd: workspace,
    encoding: "utf8"
  });
  if (result.status !== 0) {
    throw new Error(`${kicadCli} ${args.join(" ")}\n${result.stdout}\n${result.stderr}`);
  }
  return {
    stdout: result.stdout,
    stderr: result.stderr
  };
}

fs.mkdirSync(outDir, { recursive: true });

run([
  "pcb",
  "export",
  "odb",
  "--output",
  odbPath,
  "--units",
  "mm",
  "--precision",
  "6",
  boardPath
]);

run([
  "pcb",
  "export",
  "ipc2581",
  "--output",
  ipcPath,
  "--units",
  "mm",
  "--precision",
  "6",
  "--version",
  "C",
  boardPath
]);

const summary = {
  ok: true,
  preferred_hfss3dlayout_import: "ODB++",
  board: boardPath,
  odb: odbPath,
  ipc2581: ipcPath,
  notes: [
    "Use ODB++ as the primary HFSS 3D Layout import artifact.",
    "IPC-2581 is exported as a backup interchange format.",
    "KiCad CLI may print config directory warnings even when export succeeds."
  ]
};

fs.writeFileSync(path.join(outDir, "hfss3dlayout_export_summary.json"), `${JSON.stringify(summary, null, 2)}\n`, "utf8");
console.log(JSON.stringify(summary, null, 2));
