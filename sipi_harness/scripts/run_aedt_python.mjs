import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const home = os.homedir();

function unique(items) {
  const seen = new Set();
  const out = [];
  for (const item of items.filter(Boolean)) {
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

function existingAnsysPythonCandidates() {
  const roots = [
    process.env.ANSYS_INC,
    process.env.ANSYS_ROOT,
    "C:\\Program Files\\ANSYS Inc"
  ].filter(Boolean);
  for (const [key, value] of Object.entries(process.env)) {
    if (/^ANSYSEM_ROOT\d+$/i.test(key)) roots.push(path.dirname(path.dirname(value)));
  }

  const candidates = [];
  for (const root of unique(roots)) {
    if (!fs.existsSync(root)) continue;
    let versions = [];
    try {
      versions = fs.readdirSync(root, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && /^v\d+$/i.test(entry.name))
        .map((entry) => entry.name)
        .sort((a, b) => Number(b.slice(1)) - Number(a.slice(1)));
    } catch {
      continue;
    }
    for (const version of versions) {
      const base = path.join(root, version);
      candidates.push(
        path.join(base, "AnsysEM", "commonfiles", "CPython", "3_10", "winx64", "Release", "python", "python.exe"),
        path.join(base, "AnsysEM", "common", "commonfiles", "CPython", "3_10", "winx64", "python", "python.exe"),
        path.join(base, "commonfiles", "CPython", "3_10", "winx64", "Release", "python", "python.exe")
      );
    }
  }
  return unique(candidates).filter((candidate) => fs.existsSync(candidate));
}

const candidates = [
  ...existingAnsysPythonCandidates(),
  process.env.AEDT_PYTHON,
  process.env.PYAEDT_PYTHON,
  home ? `${home}\\anaconda3\\envs\\aedt_env\\python.exe` : null,
  home ? `${home}\\miniconda3\\envs\\aedt_env\\python.exe` : null,
  home ? `${home}\\mambaforge\\envs\\aedt_env\\python.exe` : null,
  process.env.PYTHON,
  "python"
].filter(Boolean);

const probe = "import ansys.aedt.core; import pyedb";
const installUrl = "https://aedt.docs.pyansys.com/version/stable/Getting_started/Installation.html";
const defaultInstallPackages = ["pyaedt", "pyedb"];

const args = process.argv.slice(2);
if (!args.length) {
  console.error("Usage: node scripts/run_aedt_python.mjs <script.py> [args...]");
  console.error("       node scripts/run_aedt_python.mjs --install-deps [pyaedt pyedb]");
  process.exit(2);
}

if (args[0] === "--install-deps") {
  const packages = args.slice(1).length ? args.slice(1) : defaultInstallPackages;
  const installCandidates = unique(candidates).filter((pythonExe) => pythonExe === "python" || fs.existsSync(pythonExe));
  const pythonExe = installCandidates[0];
  if (!pythonExe) {
    console.error(`No Python candidate found for PyAEDT install. See ${installUrl}`);
    process.exit(2);
  }
  console.error(`Installing ${packages.join(" ")} into: ${pythonExe}`);
  console.error(`Official PyAEDT installation guide: ${installUrl}`);
  const result = spawnSync(pythonExe, ["-m", "pip", "install", "-U", ...packages], {
    stdio: "inherit",
    env: process.env,
    windowsHide: true
  });
  process.exit(result.status ?? (result.error ? 1 : 0));
}

let lastError = null;
for (const pythonExe of unique(candidates)) {
  if (pythonExe !== "python" && !fs.existsSync(pythonExe)) continue;
  const probeResult = spawnSync(pythonExe, ["-c", probe], {
    stdio: "ignore",
    env: process.env,
    windowsHide: true
  });
  if (probeResult.error || probeResult.status !== 0) {
    lastError = probeResult.error || new Error(`${pythonExe} cannot import ansys.aedt.core and pyedb`);
    continue;
  }
  const result = spawnSync(pythonExe, args, {
    stdio: "inherit",
    env: process.env,
    windowsHide: true
  });
  if (!result.error) {
    process.exit(result.status ?? 0);
  }
  lastError = result.error;
}

console.error(
  [
    "AEDT/PyAEDT Python executable not found or the selected Python cannot import ansys.aedt.core and pyedb.",
    "Set AEDT_PYTHON to a validated AEDT CPython/user Python, or install the required packages.",
    `Official PyAEDT installation guide: ${installUrl}`,
    "Common install commands:",
    "  python -m pip install -U pyaedt pyedb",
    "  node sipi_harness/scripts/run_aedt_python.mjs --install-deps",
    lastError ? `Last error: ${lastError.message}` : ""
  ].filter(Boolean).join("\n")
);
process.exit(2);
