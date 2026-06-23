import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function readJson(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function readText(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return "";
  return fs.readFileSync(filePath, "utf8");
}

function inferCaseEvidenceText(caseDir, strategyPath) {
  const files = [];
  if (strategyPath) files.push(strategyPath);
  files.push(path.join(caseDir, "strategy", "design_strategy.yaml"));
  files.push(path.join(caseDir, "strategy", "wiki_fusion_input.json"));
  files.push(path.join(caseDir, "manifest.json"));
  const evidenceDir = path.join(caseDir, "spec_evidence");
  if (fs.existsSync(evidenceDir)) {
    const stack = [evidenceDir];
    while (stack.length && files.length < 60) {
      const dir = stack.pop();
      for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, item.name);
        if (item.isDirectory()) stack.push(full);
        else if (item.isFile() && /\.(json|ya?ml|md|txt)$/i.test(item.name)) files.push(full);
      }
    }
  }
  return files.map((file) => readText(file)).join("\n").toLowerCase();
}

function detectedSpecBenchFamilies(text) {
  const families = {
    "voltage transfer function / VTF": [/\bvtf\b/, /voltage\s+transfer\s+function/, /\bl\(fn\)/],
    "spec crosstalk equation": [/\bxt\(fn\)/, /power\s+sum/, /crosstalk\s+power/, /aggressor/],
    "explicit R/C loading model": [/\brtx\b/, /\bctx\b/, /\brrx\b/, /\bcrx\b/, /loading\s+model/],
    "eye mask / BER / bathtub": [/eye\s+diagram/, /eye\s+mask/, /ber\s+contour/, /\bber\b/, /bathtub/, /jitter/]
  };
  return Object.entries(families)
    .filter(([, patterns]) => patterns.some((pattern) => pattern.test(text)))
    .map(([family]) => family);
}

function existsLine(label, filePath) {
  if (!filePath) return `- ${label}: not provided`;
  const resolved = path.resolve(filePath);
  if (!fs.existsSync(resolved)) return `- ${label}: MISSING - ${resolved}`;
  const stat = fs.statSync(resolved);
  return `- ${label}: OK - ${resolved} (${stat.size} bytes)`;
}

function valueOrMissing(value) {
  return value === undefined || value === null || value === "" ? "missing" : String(value);
}

function geometryGateLine(caseDir) {
  const report = path.join(caseDir, "reports", "kicad_same_layer_geometry.json");
  if (!fs.existsSync(report)) return `- Geometry gate status: MISSING - ${path.resolve(report)}`;
  try {
    const data = readJson(report);
    const result = data?.result || "unknown";
    const violations = data?.violation_count ?? data?.violations ?? "unknown";
    return `- Geometry gate status: ${result} (${violations} violations) - ${path.resolve(report)}`;
  } catch (error) {
    return `- Geometry gate status: unreadable (${error.message}) - ${path.resolve(report)}`;
  }
}

function hfssPrompt(args, manifest) {
  const caseDir = path.resolve(String(args["case-dir"] || "."));
  const strategy = args.strategy || path.join(caseDir, "strategy", "design_strategy.yaml");
  const board = args.board || manifest?.artifacts?.kicad_pcb || manifest?.inputs?.kicad_board?.path;
  const portIntents = args["port-intents"] || manifest?.artifacts?.hfss3dlayout_port_intents || manifest?.inputs?.port_intents?.path;
  const project = args.project || path.join(caseDir, "simulation", "hfss3dlayout", `${path.basename(caseDir)}.aedt`);
  const touchstone = args.touchstone || path.join(caseDir, "simulation", "hfss3dlayout", `${path.basename(caseDir)}.sNp`);
  const dataRate = Number(args["data-rate-gbps"] || manifest?.board?.data_rate_gbps || manifest?.inputs?.data_rate_gbps || 0);
  const nyquist = dataRate ? dataRate / 2 : null;
  const stop = Number(args["stop-ghz"] || (nyquist ? 5 * nyquist : 0));
  const points = Number(args.points || 11);
  const sweepType = args["sweep-type"] || "Fast";
  const portData = readJson(portIntents);
  const portCount = portData?.ports?.length ?? manifest?.ports ?? "missing";

  return `# HFSS 3D Layout Setup Review

Stage Review Mode must pause here before running the HFSS solve.

## Stage Goal

Create or open a non-empty AEDB/AEDT design, verify stackup/nets/primitives,
verify ${valueOrMissing(portCount)} expected ports from port intent, configure a
fast smoke sweep, and export a non-empty Touchstone file. This stage is not
complete until Touchstone port count/order/frequency range are validated.

## Inputs and Artifacts

${existsLine("Design strategy", strategy)}
${existsLine("KiCad board/package", board)}
${geometryGateLine(caseDir)}
${existsLine("Port intent JSON", portIntents)}
- AEDT project target: ${path.resolve(project)}
- Touchstone target: ${path.resolve(touchstone)}

## Proposed HFSS Setup

- AEDT version: ${valueOrMissing(args.version || "2025.1")}
- Port method: ${valueOrMissing(args["port-method"] || "edb_polygon_edge")}
- Sweep type: ${sweepType}
- Data rate: ${dataRate ? `${dataRate} Gbps` : "missing"}
- Nyquist: ${nyquist ? `${nyquist} GHz` : "missing"}
- Stop frequency: ${stop ? `${stop} GHz` : "missing"} (default rule: at least 5x Nyquist)
- Points: ${points} (fast/smoke; not compliance)
- Start frequency: ${valueOrMissing(args["start-ghz"] || "0.1")} GHz
- Expected port count: ${valueOrMissing(portCount)}

## Review Checklist

- Strategy and pre-PCB report exist.
- Board/package file exists and geometry gate passed or is explicitly proxy.
- If geometry gate status is FAIL, do not approve HFSS solve; reroute or mark
  the layout blocked/proxy first.
- Stackup has continuous reference layers for every routed high-speed segment.
- If the latest route repair removed or fragmented reference planes, do not
  approve HFSS solve; return to PCB/package generation first.
- Port intent lists signal net, reference net/layer, coordinate/pad, type, and order.
- Default import uses AEDB polygon-edge circuit ports (\`edb_polygon_edge\`):
  signal primitive edge to local reference primitive/edge. Coordinate or pin
  ports require explicit override and manual/tool evidence because they can be
  misplaced after import.
- Import path will stop if AEDB is empty or if port list is empty after reopen.
- Fast sweep is accepted only as smoke evidence; compliance requires engineering/compliance sweep settings.
- Touchstone will be checked for non-empty data, expected port count, port order, and frequency range.

## Approval Question

Approve this HFSS setup and run the fast solve now, or request changes?
`;
}

function pcbPrompt(args, manifest) {
  const caseDir = path.resolve(String(args["case-dir"] || "."));
  const board = args.board || manifest?.artifacts?.kicad_pcb || manifest?.inputs?.kicad_board?.path;
  const strategy = args.strategy || manifest?.artifacts?.design_strategy_yaml || path.join(caseDir, "strategy", "design_strategy.yaml");
  const preview = args.preview || manifest?.artifacts?.kicad_layout_preview_png || path.join(caseDir, "reports", "kicad_layout_preview.png");
  const portIntents = args["port-intents"] || manifest?.artifacts?.hfss3dlayout_port_intents || manifest?.inputs?.port_intents?.path;

  return `# PCB / Package Layout Review

Stage Review Mode must pause here after KiCad/package generation and before EM handoff.

## Stage Goal

Generate a complete layout bundle, verify geometry gates, create explicit HFSS
port intent, and render a board/package preview image for human review. This
stage is not complete until the preview image, geometry status, and port intent
are reviewable.

## Inputs and Artifacts

${existsLine("Design strategy", strategy)}
${existsLine("KiCad board/package", board)}
${existsLine("Layout preview image", preview)}
${existsLine("Same-layer geometry check", path.join(caseDir, "reports", "kicad_same_layer_geometry.json"))}
${geometryGateLine(caseDir)}
${existsLine("Port intent JSON", portIntents)}

## Required Visual Review

- Show the preview image to the engineer in the review message when possible.
- Confirm pad/bump placement, route crossings, route ordering, layer usage,
  board/package outline, launch/port locations, and obvious clearance issues.
- Confirm high-speed routes kept \`allow_diagonal: true\` or have an approved
  exception. Avoidable orthogonal-only/90-degree routing is not reviewable.
- Confirm every routed high-speed channel has a continuous assigned reference
  plane/layer. Local GND launch tabs or port tabs are not the channel reference
  plane.
- The image is a review aid. DRC, route records, and the same-layer geometry
  checker remain the machine-readable signoff evidence.
- If geometry gate status is FAIL, do not hand off to HFSS as a valid candidate.

## Required Geometry and Preview Commands

\`\`\`powershell
cd <repo>\\sipi_harness
npm run check:kicad-geometry -- --board <board.kicad_pcb> --output <case-dir>\\reports\\kicad_same_layer_geometry.json --manifest <case-dir>\\manifest.json
npm run render:kicad-preview -- --board <board.kicad_pcb> --output <case-dir>\\reports\\kicad_layout_preview.png --manifest <case-dir>\\manifest.json
\`\`\`

Do not approve HFSS handoff unless \`kicad_same_layer_geometry.json\` reports
\`PASS\`, or the case is explicitly marked proxy/blocked and not a valid EM
candidate.

## Approval Question

Approve this PCB/package layout for HFSS handoff, or request routing/geometry changes?
`;
}

function adsPrompt(args, manifest) {
  const caseDir = path.resolve(String(args["case-dir"] || "."));
  const touchstone = args.touchstone || manifest?.artifacts?.touchstone || manifest?.inputs?.touchstone?.path || path.join(caseDir, "simulation", "hfss3dlayout", `${path.basename(caseDir)}.sNp`);
  const workspace = args.workspace || path.join(caseDir, "bench", "sparameter_wrk");
  const strategy = args.strategy || path.join(caseDir, "strategy", "design_strategy.yaml");
  const benchType = args["bench-type"] || "blocked until strategy-selected spec bench or diagnostic fallback";
  const specMode = args["spec-mode"] || "blocked_until_spec_bench_confirmed";
  const evidenceText = inferCaseEvidenceText(caseDir, strategy);
  const specFamilies = detectedSpecBenchFamilies(evidenceText);
  const fallbackRequested = /s-parameter fallback|sparameter|spec-neutral/i.test(benchType);
  const fallbackBlocked = fallbackRequested && specFamilies.length > 0;
  const blockedText = fallbackBlocked
    ? `
## Fallback Blocked

Spec-defined benchmark evidence was detected:

${specFamilies.map((family) => `- ${family}`).join("\n")}

Do not run \`npm run bench:sparameter\` as the Bench stage result. Implement the
exact spec-defined ADS/circuit benchmark, including loading/equations and
eye/mask/BER outputs where required, or mark Bench blocked. A spec-neutral
S-parameter report may be created only as an explicit diagnostic supplement
with \`--allow-spec-neutral-fallback --fallback-reason <reason>\`.
`
    : "";

  return `# Bench / ADS Verification Review

Stage Review Mode must pause here before running ADS or benchmark verification.

## Stage Goal

Create an inspectable benchmark workspace, copy the Touchstone into the
workspace data folder, validate file syntax and port mapping, run the selected
frequency-domain or transient-domain benchmark, and write plots plus JSON/PDF
reports. This stage is not complete until report artifacts exist and the result
is labeled compliance, proxy, or blocked.

## Inputs and Artifacts

${existsLine("Design strategy", strategy)}
${existsLine("Touchstone input", touchstone)}
- Benchmark workspace target: ${path.resolve(workspace)}

## Proposed Bench Setup

- Bench type: ${benchType}
- Result mode: ${specMode}
- Touchstone filename rule: copy into workspace data folder; use plain filename, no @ prefix.
- Default fallback metrics only when no reviewed spec bench exists:
  - insertion loss
  - return loss
  - crosstalk when port count supports multi-lane analysis
${blockedText}
- Multi-lane rule: for lane-count N, a spec crosstalk/eye bench must use the
  full S(2N)P Touchstone, run every required victim lane, and include all N-1
  aggressors unless the governing spec explicitly defines a reduced method.
  A 3-lane `.s6p` template is only a smoke baseline.
- Required outputs:
  - spec-defined metric plots and JSON/PDF when spec benches exist
  - reports/sparameter_bench_report.pdf only for diagnostic fallback
  - reports/sparameter_bench_summary.json only for diagnostic fallback
  - metric PNG plots

## Review Checklist

- Governing spec equations/loading model are available if compliance is claimed.
- If spec equations are missing, the run is explicitly proxy/sanity evidence.
- If spec equations/loading/eye requirements are present, S-parameter fallback
  is not accepted as the Bench stage result.
- Touchstone port count/order and reference impedance are understood.
- ADS workspace path, data folder, and filename syntax are valid.
- Schematic/netlist connectivity must be checked before claiming schematic validity.
- Dataset/DDS/report paths must resolve without missing dataset warnings.

## Approval Question

Approve this benchmark setup and run ADS/bench verification now, or request changes?
`;
}

const args = parseArgs(process.argv.slice(2));
const stage = String(args.stage || "").toLowerCase();
const manifest = readJson(args.manifest || (args["case-dir"] ? path.join(args["case-dir"], "manifest.json") : null));

if (["pcb", "pcb_package", "kicad", "layout"].includes(stage)) {
  console.log(pcbPrompt(args, manifest));
} else if (["hfss", "hfss_setup", "em", "em_solve"].includes(stage)) {
  console.log(hfssPrompt(args, manifest));
} else if (["ads", "bench", "verification", "ads_verification"].includes(stage)) {
  console.log(adsPrompt(args, manifest));
} else {
  console.error("Usage: node scripts/print_stage_review_prompt.mjs --stage pcb|hfss|ads --case-dir <case-dir> [stage-specific args]");
  process.exit(2);
}
