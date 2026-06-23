import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith("--")) continue;
    const key = argv[i].slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
    args[key] = value;
  }
  return args;
}

function listFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const filePath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...listFiles(filePath));
    } else if (entry.isFile() && entry.name !== ".gitkeep") {
      out.push(filePath);
    }
  }
  return out.sort();
}

function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function readJson(filePath, fallback) {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

const args = parseArgs(process.argv.slice(2));
const caseDir = path.resolve(args["case-dir"] || path.join(root, "knowledge_intake"));
const intakeDir = path.basename(caseDir) === "knowledge_intake" ? caseDir : path.join(caseDir, "knowledge_intake");
const userDir = path.join(intakeDir, "user_references");
const webDir = path.join(intakeDir, "web_research");
const fusionDir = path.join(intakeDir, "wiki_fusion");
const statePath = path.join(fusionDir, "source_state.json");
const queuePath = path.join(intakeDir, "ingest_queue.json");
const includeWikiRaw = args["include-wiki-raw"] !== "false";
const wikiRawDir = path.join(root, "wiki", "raw");
const excludedWikiRawDirs = new Set(["extracted_evidence"]);

fs.mkdirSync(fusionDir, { recursive: true });

const previous = readJson(statePath, { sources: [] });
const previousByPath = new Map((previous.sources || []).map((item) => [item.path, item]));
const wikiRawFiles = includeWikiRaw
  ? fs.readdirSync(wikiRawDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !excludedWikiRawDirs.has(entry.name))
      .flatMap((entry) => listFiles(path.join(wikiRawDir, entry.name)))
  : [];
const files = [...listFiles(userDir), ...listFiles(webDir), ...wikiRawFiles]
  .filter((filePath) => !filePath.endsWith("_registry.json") && !filePath.endsWith("README.md"));
const sources = files.map((filePath) => {
  const stat = fs.statSync(filePath);
  const relative = filePath.startsWith(intakeDir)
    ? path.relative(intakeDir, filePath).replaceAll("\\", "/")
    : `wiki_raw/${path.relative(wikiRawDir, filePath).replaceAll("\\", "/")}`;
  const digest = sha256(filePath);
  const prior = previousByPath.get(relative);
  return {
    path: relative,
    absolute_path: filePath,
    sha256: digest,
    bytes: stat.size,
    mtime_ms: stat.mtimeMs,
    status: prior?.sha256 === digest ? "unchanged" : "changed"
  };
});

const queue = readJson(queuePath, {
  schema_version: "0.1",
  kind: "ingest_queue",
  status: "idle",
  policy: { serial_processing: true, max_retries: 3, skip_unchanged_sha256: true },
  items: []
});
const queued = new Set((queue.items || []).map((item) => item.path));
for (const item of sources.filter((source) => source.status === "changed")) {
  if (queued.has(item.path)) continue;
  queue.items.push({
    path: item.path,
    absolute_path: item.absolute_path,
    sha256: item.sha256,
    status: "pending",
    attempts: 0,
    action: "docling_or_pdf_extract_then_review_then_generate_typed_cards"
  });
}

writeJson(statePath, {
  schema_version: "0.1",
  kind: "source_state",
  intake_dir: intakeDir,
  wiki_raw_dir: includeWikiRaw ? wikiRawDir : null,
  generated_at: new Date().toISOString(),
  sources
});
writeJson(queuePath, queue);

console.log(JSON.stringify({
  intake_dir: intakeDir,
  source_state: statePath,
  ingest_queue: queuePath,
  source_count: sources.length,
  changed_count: sources.filter((item) => item.status === "changed").length,
  queued_count: queue.items.length
}, null, 2));
