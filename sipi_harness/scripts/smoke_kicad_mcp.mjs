import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const repo = path.resolve("..", "KiCAD-MCP-Server-main-src", "KiCAD-MCP-Server-main");
const nodeExe = "C:\\Program Files\\nodejs\\node.exe";
const kicadBin = "C:\\Program Files\\KiCad\\9.0\\bin";
const mcpHome = path.resolve("..", "outputs", "kicad_mcp_home");
const appData = path.join(mcpHome, "AppData", "Roaming");
const localAppData = path.join(mcpHome, "AppData", "Local");
const depsPath = path.join(repo, ".python-deps");
const backendPath = path.join(repo, "python");
const observedKiCadUserSite = path.resolve("KiCad", "9.0", "3rdparty", "Python311", "site-packages");
const mcpHomeKiCadUserSite = path.join(mcpHome, "Documents", "KiCad", "9.0", "3rdparty", "Python311", "site-packages");

fs.mkdirSync(path.join(appData, "kicad", "9.0"), { recursive: true });
fs.mkdirSync(path.join(localAppData, "kicad", "9.0"), { recursive: true });
fs.mkdirSync(path.join(mcpHome, ".kicad-mcp", "logs"), { recursive: true });
for (const userSite of [observedKiCadUserSite, mcpHomeKiCadUserSite]) {
  fs.mkdirSync(userSite, { recursive: true });
  fs.writeFileSync(path.join(userSite, "sipi_kicad_mcp.pth"), `${depsPath}\n${backendPath}\n`, "utf8");
}

const mcpEnv = {
  ...process.env,
  PATH: `${kicadBin};C:\\Program Files\\nodejs;${process.env.PATH || ""}`,
  KICAD_PYTHON: `${kicadBin}\\python.exe`,
  PYTHONPATH: `${depsPath};${backendPath};${kicadBin}\\Lib\\site-packages`,
  NODE_ENV: "production",
  LOG_LEVEL: "warn",
  KICAD_MCP_LOG_LEVEL: "warn",
  KICAD_AUTO_LAUNCH: "false",
  KICAD_MCP_DEV: "0",
  USERPROFILE: mcpHome,
  HOME: mcpHome,
  APPDATA: appData,
  LOCALAPPDATA: localAppData
};

const preflight = spawnSync(
  `${kicadBin}\\python.exe`,
  ["-c", "import os,sys; print(os.environ.get('PYTHONPATH')); print(sys.path); import sexpdata; print('sexpdata ok')"],
  { env: mcpEnv, encoding: "utf8" }
);

const child = spawn(nodeExe, ["dist/index.js"], {
  cwd: repo,
  env: mcpEnv,
  stdio: ["pipe", "pipe", "pipe"]
});

let stdout = "";
let stderr = "";

child.stdout.on("data", (chunk) => {
  stdout += chunk.toString();
});
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function parseFrames(data) {
  return data
    .split(/\r?\n/)
    .filter((line) => line.trim().startsWith("{"))
    .map((line) => JSON.parse(line));
}

await new Promise((resolve) => setTimeout(resolve, 1500));

send({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "sipi-harness-smoke", version: "0.1" }
  }
});

await new Promise((resolve) => setTimeout(resolve, 500));
send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });
send({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });

await new Promise((resolve) => setTimeout(resolve, 3000));
child.kill();
await new Promise((resolve) => child.on("exit", resolve));

const messages = parseFrames(stdout);
const initialize = messages.find((message) => message.id === 1);
const tools = messages.find((message) => message.id === 2)?.result?.tools || [];

console.log(
  JSON.stringify(
    {
      ok: Boolean(initialize?.result) && tools.length > 0,
      toolCount: tools.length,
      firstTools: tools.slice(0, 20).map((tool) => tool.name),
      repo,
      pythonpath: `${repo}\\.python-deps;${repo}\\python;${kicadBin}\\Lib\\site-packages`,
      pthSites: [observedKiCadUserSite, mcpHomeKiCadUserSite],
      preflight: {
        status: preflight.status,
        stdout: preflight.stdout.trim(),
        stderr: preflight.stderr.trim()
      },
      stderrTail: stderr.slice(-1200)
    },
    null,
    2
  )
);
