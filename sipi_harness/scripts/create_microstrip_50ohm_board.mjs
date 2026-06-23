import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const workspace = path.resolve("..");
const repo = path.join(workspace, "KiCAD-MCP-Server-main-src", "KiCAD-MCP-Server-main");
const nodeExe = process.execPath;
const kicadBin = "C:\\Program Files\\KiCad\\9.0\\bin";
const mcpHome = path.join(workspace, "outputs", "kicad_mcp_home");
const appData = path.join(mcpHome, "AppData", "Roaming");
const localAppData = path.join(mcpHome, "AppData", "Local");
const depsPath = path.join(repo, ".python-deps");
const backendPath = path.join(repo, "python");
const projectRoot = path.join(workspace, "outputs", "kicad_microstrip_50ohm");

const board = {
  projectName: "microstrip_50ohm_fr4_1p6",
  widthMm: 80,
  heightMm: 40,
  traceWidthMm: 2.986,
  substrateHeightMm: 1.6,
  er: 4.3,
  copperThicknessMm: 0.035,
  z0ApproxOhm: 49.99
};

function kid() {
  return crypto.randomUUID();
}

function writeDirectBoardFallback(reason) {
  fs.mkdirSync(projectRoot, { recursive: true });
  const projectPath = path.join(projectRoot, `${board.projectName}.kicad_pro`);
  const boardPath = path.join(projectRoot, `${board.projectName}.kicad_pcb`);
  const summaryPath = path.join(projectRoot, "microstrip_50ohm_summary.json");

  fs.writeFileSync(
    projectPath,
    `${JSON.stringify(
      {
        meta: { filename: `${board.projectName}.kicad_pro`, version: 1 },
        board: { design_settings: { defaults: { board_outline_line_width: 0.1 } } }
      },
      null,
      2
    )}\n`,
    "utf8"
  );

  const pcb = `(kicad_pcb
\t(version 20241229)
\t(generator "sipi-harness-direct-fallback")
\t(generator_version "0.1")
\t(general
\t\t(thickness 1.635)
\t)
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user)
\t\t(33 "F.Adhes" user)
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user)
\t\t(37 "F.SilkS" user)
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(44 "Edge.Cuts" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer "dielectric 1"
\t\t\t\t(type "core")
\t\t\t\t(thickness 1.6)
\t\t\t\t(material "FR4")
\t\t\t\t(epsilon_r 4.3)
\t\t\t\t(loss_tangent 0.02)
\t\t\t)
\t\t\t(layer "B.Cu"
\t\t\t\t(type "copper")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t)
\t)
\t(net 0 "")
\t(net 1 "SIG_50OHM")
\t(net 2 "GND")
\t(gr_line (start 0 0) (end 80 0) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "${kid()}"))
\t(gr_line (start 80 0) (end 80 40) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "${kid()}"))
\t(gr_line (start 80 40) (end 0 40) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "${kid()}"))
\t(gr_line (start 0 40) (end 0 0) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "${kid()}"))
\t(segment (start 5 20) (end 10 20) (width 5.0) (layer "F.Cu") (net 1) (uuid "${kid()}"))
\t(segment (start 10 20) (end 70 20) (width ${board.traceWidthMm}) (layer "F.Cu") (net 1) (uuid "${kid()}"))
\t(segment (start 70 20) (end 75 20) (width 5.0) (layer "F.Cu") (net 1) (uuid "${kid()}"))
\t(gr_text "50 ohm microstrip: FR4 er=4.3, h=1.6mm, W=2.986mm, Cu=35um"
\t\t(at 6 8 0)
\t\t(layer "F.SilkS")
\t\t(effects (font (size 1.4 1.4) (thickness 0.15)))
\t\t(uuid "${kid()}")
\t)
\t(gr_text "B.Cu solid GND reference plane"
\t\t(at 6 34 0)
\t\t(layer "F.SilkS")
\t\t(effects (font (size 1.2 1.2) (thickness 0.15)))
\t\t(uuid "${kid()}")
\t)
\t(zone
\t\t(net 2)
\t\t(net_name "GND")
\t\t(layer "B.Cu")
\t\t(uuid "${kid()}")
\t\t(hatch edge 0.5)
\t\t(connect_pads
\t\t\t(clearance 0.25)
\t\t)
\t\t(min_thickness 0.25)
\t\t(filled_areas_thickness no)
\t\t(fill yes
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t(xy 2 2)
\t\t\t\t(xy 78 2)
\t\t\t\t(xy 78 38)
\t\t\t\t(xy 2 38)
\t\t\t)
\t\t)
\t)
)
`;
  fs.writeFileSync(boardPath, pcb, "utf8");

  const steps = [{ name: "direct_kicad_file_fallback", ok: true, reason }];
  fs.writeFileSync(summaryPath, `${JSON.stringify({ board, projectRoot, steps }, null, 2)}\n`, "utf8");
  console.log(
    JSON.stringify(
      {
        ok: true,
        mode: "direct_kicad_file_fallback",
        reason,
        projectRoot,
        projectFile: projectPath,
        boardFile: boardPath,
        summaryPath,
        board,
        steps
      },
      null,
      2
    )
  );
}

const mcpEntrypoint = path.join(repo, "dist", "index.js");
if (!fs.existsSync(mcpEntrypoint)) {
  writeDirectBoardFallback(`KiCad MCP server not found at ${mcpEntrypoint}`);
  process.exit(0);
}

function setupEnv() {
  fs.mkdirSync(path.join(appData, "kicad", "9.0"), { recursive: true });
  fs.mkdirSync(path.join(localAppData, "kicad", "9.0"), { recursive: true });
  fs.mkdirSync(path.join(mcpHome, ".kicad-mcp", "logs"), { recursive: true });
  const userSite = path.join(mcpHome, "Documents", "KiCad", "9.0", "3rdparty", "Python311", "site-packages");
  fs.mkdirSync(userSite, { recursive: true });
  fs.writeFileSync(path.join(userSite, "sipi_kicad_mcp.pth"), `${depsPath}\n${backendPath}\n`, "utf8");

  return {
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
}

const child = spawn(nodeExe, ["dist/index.js"], {
  cwd: repo,
  env: setupEnv(),
  stdio: ["pipe", "pipe", "pipe"]
});

let stdout = "";
let stderr = "";
let nextId = 1;

child.stdout.on("data", (chunk) => {
  stdout += chunk.toString();
});
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

function parseFrames() {
  return stdout
    .split(/\r?\n/)
    .filter((line) => line.trim().startsWith("{"))
    .map((line) => JSON.parse(line));
}

async function waitFor(id, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const found = parseFrames().find((message) => message.id === id);
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for JSON-RPC id ${id}`);
}

async function rpc(method, params = {}, timeoutMs = 20000) {
  const id = nextId++;
  send({ jsonrpc: "2.0", id, method, params });
  const response = await waitFor(id, timeoutMs);
  if (response.error) throw new Error(`${method}: ${JSON.stringify(response.error)}`);
  return response.result;
}

async function callTool(name, args = {}, timeoutMs = 30000) {
  const result = await rpc("tools/call", { name, arguments: args }, timeoutMs);
  if (result?.isError) {
    throw new Error(`${name}: ${JSON.stringify(result)}`);
  }
  return result;
}

await new Promise((resolve) => setTimeout(resolve, 1500));
await rpc("initialize", {
  protocolVersion: "2025-06-18",
  capabilities: {},
  clientInfo: { name: "sipi-microstrip-generator", version: "0.1" }
});
send({ jsonrpc: "2.0", method: "notifications/initialized", params: {} });

fs.mkdirSync(path.dirname(projectRoot), { recursive: true });

const steps = [];
async function step(name, args, timeoutMs) {
  const directArgTools = new Set(["create_project", "save_project", "snapshot_project"]);
  let toolArgs = directArgTools.has(name) ? args : { params: { ...args, unit: "mm" } };
  if (name === "add_board_outline") {
    const { shape, ...params } = args;
    toolArgs = { shape, params: { ...params, unit: "mm" } };
  }
  if (name === "add_copper_pour") {
    const { netName, layer, ...params } = args;
    toolArgs = { net: netName, layer, params: { ...params, unit: "mm" } };
  }
  if (name === "route_trace") {
    const [startPoint, endPoint] = args.points;
    toolArgs = {
      net: args.netName,
      layer: args.layer,
      width: args.width,
      start: { x: startPoint[0], y: startPoint[1] },
      end: { x: endPoint[0], y: endPoint[1] },
      params: { unit: "mm" }
    };
  }
  if (name === "add_board_text") {
    toolArgs = {
      text: args.text,
      position: { x: args.x, y: args.y, unit: "mm" },
      layer: args.layer || "F.SilkS",
      size: args.size || 1.0,
      thickness: args.thickness,
      params: { unit: "mm" }
    };
  }
  const result = await callTool(name, toolArgs, timeoutMs);
  steps.push({ name, ok: true });
  return result;
}

try {
  await step("create_project", {
    name: board.projectName,
    path: projectRoot
  });
  await step("add_board_outline", {
    shape: "rectangle",
    x: 0,
    y: 0,
    width: board.widthMm,
    height: board.heightMm
  });
  await step("add_copper_pour", {
    netName: "GND",
    layer: "B.Cu",
    clearance: 0.25,
    outline: [
      [2, 2],
      [78, 2],
      [78, 38],
      [2, 38]
    ]
  });
  await step("route_trace", {
    netName: "SIG_50OHM",
    layer: "F.Cu",
    width: 5.0,
    points: [
      [5, 20],
      [10, 20]
    ]
  });
  await step("route_trace", {
    netName: "SIG_50OHM",
    layer: "F.Cu",
    width: board.traceWidthMm,
    points: [
      [10, 20],
      [70, 20]
    ]
  });
  await step("route_trace", {
    netName: "SIG_50OHM",
    layer: "F.Cu",
    width: 5.0,
    points: [
      [70, 20],
      [75, 20]
    ]
  });
  await step("add_board_text", {
    text: "50 ohm microstrip: FR4 er=4.3, h=1.6mm, W=2.986mm, Cu=35um",
    x: 6,
    y: 8,
    layer: "F.SilkS",
    size: 1.4,
    thickness: 0.15
  });
  await step("add_board_text", {
    text: "B.Cu solid GND reference plane",
    x: 6,
    y: 34,
    layer: "F.SilkS",
    size: 1.2,
    thickness: 0.15
  });
  await step("save_project", {});
  await step("snapshot_project", { label: "microstrip_50ohm_layout", step: "microstrip_50ohm_layout" });

  const summaryPath = path.join(projectRoot, "microstrip_50ohm_summary.json");
  fs.writeFileSync(summaryPath, `${JSON.stringify({ board, projectRoot, steps }, null, 2)}\n`, "utf8");

  console.log(
    JSON.stringify(
      {
        ok: true,
        projectRoot,
        boardFile: path.join(projectRoot, `${board.projectName}.kicad_pcb`),
        summaryPath,
        board,
        steps,
        stderrTail: stderr.slice(-1000)
      },
      null,
      2
    )
  );
} finally {
  child.kill();
}
