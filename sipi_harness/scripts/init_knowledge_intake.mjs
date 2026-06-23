import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

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

function safeCaseName(value) {
  return String(value || "case")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 96) || "case";
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  const keep = path.join(dir, ".gitkeep");
  if (!fs.existsSync(keep)) fs.writeFileSync(keep, "", "utf8");
}

function readJsonOrEmpty(filePath) {
  if (!fs.existsSync(filePath)) return {};
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function updateManifest(caseDir, payload) {
  const manifestPath = path.join(caseDir, "manifest.json");
  const manifest = readJsonOrEmpty(manifestPath);
  manifest.knowledge_intake = {
    ...(manifest.knowledge_intake || {}),
    ...payload
  };
  writeJson(manifestPath, manifest);
}

const args = parseArgs(process.argv.slice(2));
const request = String(args.request || "").trim();
const caseName = safeCaseName(args["case-name"] || args.case || "case");
const caseDir = path.resolve(args["case-dir"] || path.join(root, "..", "outputs", caseName));
const intakeDir = path.join(caseDir, "knowledge_intake");
const webDir = path.join(intakeDir, "web_research");
const userDir = path.join(intakeDir, "user_references");
const fusionDir = path.join(intakeDir, "wiki_fusion");

for (const dir of [intakeDir, webDir, userDir, fusionDir]) ensureDir(dir);

const webRegistry = {
  schema_version: "0.1",
  kind: "web_research_registry",
  case: caseName,
  request,
  instructions: [
    "Before design, search the web for current and credible SI/PI design strategy material related to the request.",
    "Prefer primary/credible sources: standards bodies, EDA vendors, semiconductor vendors, application notes, conference/tutorial material, and reputable engineering journals.",
    "Store summaries, URLs, access dates, key claims, equations, design rules, verification methods, and cautions. Avoid copying long copyrighted passages.",
    "Record which claims are used in the design_strategy.yaml and which are only background."
  ],
  search_queries: [],
  sources: []
};

const userRegistry = {
  schema_version: "0.1",
  kind: "user_reference_registry",
  case: caseName,
  request,
  instructions: [
    "Put user-approved PDFs, books, notes, datasheets, and specs for this case under user_references/.",
    "For copyrighted or restricted material, keep source files local and do not commit them.",
    "If the source is PDF, DOCX, PPTX, XLSX, HTML, EPUB, image, Markdown/text, CSV, email, XML, or LaTeX, optionally run `npm run ingest:docling -- --case-dir <case-dir> --source-tier <tier> <source>` to create reviewed-evidence candidates.",
    "Extract text, tables, equations, figures, and page/figure/table evidence into case-local spec_evidence/ or processed reference JSON.",
    "The wiki fusion step must cite page/figure/table identifiers when a design rule comes from a user reference."
  ],
  references: []
};

const fusionInput = {
  schema_version: "0.1",
  kind: "wiki_fusion_input",
  case: caseName,
  request,
  web_research_registry: path.relative(caseDir, path.join(webDir, "web_research_registry.json")),
  user_reference_registry: path.relative(caseDir, path.join(userDir, "user_reference_registry.json")),
  output_strategy: "strategy/design_strategy.yaml",
  output_report: "strategy/pre_pcb_wiki_design_strategy_report.pdf",
  fusion_rules: [
    "Use web research for current design practice and cross-checking.",
    "Use user references/spec PDFs for governing requirements, exact limits, maps, masks, loading models, and equations.",
    "When web and user references conflict, governing spec/user reference wins for compliance; record the conflict.",
    "Only promote claims into the LLM wiki or design strategy when the source, scope, assumptions, and verification implication are recorded."
  ]
};

const ingestQueue = {
  schema_version: "0.1",
  kind: "ingest_queue",
  case: caseName,
  status: "idle",
  policy: {
    serial_processing: true,
    max_retries: 3,
    skip_unchanged_sha256: true
  },
  items: []
};

const sourceState = {
  schema_version: "0.1",
  kind: "source_state",
  case: caseName,
  sources: []
};

writeJson(path.join(webDir, "web_research_registry.json"), webRegistry);
writeJson(path.join(userDir, "user_reference_registry.json"), userRegistry);
writeJson(path.join(fusionDir, "wiki_fusion_input.json"), fusionInput);
writeJson(path.join(intakeDir, "ingest_queue.json"), ingestQueue);
writeJson(path.join(fusionDir, "source_state.json"), sourceState);

const plan = `# Knowledge Intake Plan

Case: ${caseName}

## User Request

${request || "(not provided)"}

## Required Intake Before Layout

1. Ask for missing design information: spec/version/source, interface, lanes, data rate, stackup/materials, channel length, pin/ball map source, compliance benches, and local tool versions.
2. Optional source upload: place user-provided or user-approved documents in \`user_references/\`, or place reusable local sources under \`sipi_harness/wiki/raw/\`.
3. Optional Docling conversion: run \`npm run ingest:docling -- --case-dir <case-dir> --source-tier <tier> <source>\` for PDF, DOCX, PPTX, XLSX, HTML, EPUB, image, Markdown/text, CSV, email, XML, or LaTeX sources.
4. Web research: collect current SI/PI design strategy data and store it in \`web_research/web_research_registry.json\`.
5. Wiki fusion: combine web research and user references into \`wiki_fusion/wiki_fusion_input.json\`, then generate \`strategy/design_strategy.yaml\` and the pre-PCB strategy report.
6. Source cache: run \`npm run scan:knowledge -- --case-dir <case-dir>\` to update SHA256 source state and queue candidates.
7. Graph update: after reusable claims are curated, run \`npm run register:knowledge\` and \`npm run build:graph\`.

Do not start PCB/package layout until this intake is complete or the case is explicitly marked as proxy/planning-only.
`;

fs.writeFileSync(path.join(intakeDir, "README.md"), plan, "utf8");
updateManifest(caseDir, {
  status: "initialized",
  path: intakeDir,
  web_research_registry: path.join(webDir, "web_research_registry.json"),
  user_reference_registry: path.join(userDir, "user_reference_registry.json"),
  wiki_fusion_input: path.join(fusionDir, "wiki_fusion_input.json"),
  ingest_queue: path.join(intakeDir, "ingest_queue.json"),
  source_state: path.join(fusionDir, "source_state.json")
});

console.log(JSON.stringify({
  case_dir: caseDir,
  knowledge_intake: intakeDir,
  web_research_registry: path.join(webDir, "web_research_registry.json"),
  user_reference_registry: path.join(userDir, "user_reference_registry.json"),
  wiki_fusion_input: path.join(fusionDir, "wiki_fusion_input.json"),
  ingest_queue: path.join(intakeDir, "ingest_queue.json"),
  source_state: path.join(fusionDir, "source_state.json")
}, null, 2));
