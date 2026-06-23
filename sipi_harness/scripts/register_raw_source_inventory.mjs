import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rawRoot = path.join(root, "wiki", "raw");
const sourcePath = path.join(root, "data", "sources.json");
const inventoryPath = path.join(root, "data", "raw_source_inventory.json");

const SUPPORTED_FOR_INGEST = new Set([
  ".pdf",
  ".docx",
  ".pptx",
  ".xlsx",
  ".html",
  ".htm",
  ".epub",
  ".png",
  ".jpg",
  ".jpeg",
  ".tif",
  ".tiff",
  ".md",
  ".markdown",
  ".txt",
  ".text",
  ".csv",
  ".eml",
  ".msg",
  ".xml",
  ".tex"
]);

const EXCLUDED_DIRS = new Set(["extracted_evidence"]);

function safeId(value) {
  return String(value || "raw_source")
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 120) || "raw_source";
}

function listFiles(dir, rootDir = dir, warnings = []) {
  if (!fs.existsSync(dir)) return { files: [], warnings };
  const files = [];
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (error) {
    warnings.push({ path: path.relative(rootDir, dir).replaceAll("\\", "/"), error: String(error.message || error) });
    return { files, warnings };
  }
  for (const entry of entries) {
    const filePath = path.join(dir, entry.name);
    const rel = path.relative(rootDir, filePath).replaceAll("\\", "/");
    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) continue;
      const nested = listFiles(filePath, rootDir, warnings);
      files.push(...nested.files);
    } else if (entry.isFile() && entry.name !== ".gitkeep" && entry.name !== "README.md") {
      files.push({ path: filePath, rel });
    }
  }
  return { files, warnings };
}

function sha256Maybe(filePath, maxBytes = 32 * 1024 * 1024) {
  const stat = fs.statSync(filePath);
  if (stat.size > maxBytes) return null;
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function conceptFromToken(token) {
  const value = String(token || "").replace(/[_-]+/g, " ").trim();
  if (!value) return null;
  const lower = value.toLowerCase();
  const known = [
    ["datasheet", "Datasheet"],
    ["paper", "Paper"],
    ["web research", "Web Research"],
    ["user notes", "User Notes"],
    ["spec", "Specification"],
    ["sipi", "SI/PI"],
    ["si", "Signal Integrity"],
    ["pi", "Power Integrity"],
    ["hbm", "HBM"],
    ["ucie", "UCIe"],
    ["pcie", "PCIe"],
    ["cxl", "CXL"],
    ["ddr", "DDR"],
    ["lpddr", "LPDDR"],
    ["jedec", "JEDEC"],
    ["hfss", "HFSS"],
    ["ads", "ADS"],
    ["kicad", "KiCad"]
  ];
  for (const [needle, label] of known) {
    if (lower.includes(needle)) return label;
  }
  return value.slice(0, 80);
}

function groupKey(relPath) {
  const parts = relPath.split("/");
  const top = parts[0] || "raw";
  const second = parts[1] && !parts[1].includes(".") ? parts[1] : "_root";
  return `${top}/${second}`;
}

function extensionSummary(files) {
  const counts = new Map();
  for (const file of files) {
    const ext = path.extname(file.path).toLowerCase() || file.extension || "(none)";
    counts.set(ext, (counts.get(ext) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([extension, count]) => ({ extension, count }));
}

function groupFiles(files) {
  const groups = new Map();
  for (const file of files) {
    const key = groupKey(file.path);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(file);
  }
  return groups;
}

const { files, warnings } = listFiles(rawRoot, rawRoot);
const inventoryFiles = [];
for (const file of files) {
  let stat;
  try {
    stat = fs.statSync(file.path);
  } catch (error) {
    warnings.push({ path: file.rel, error: String(error.message || error) });
    continue;
  }
  const ext = path.extname(file.rel).toLowerCase();
  inventoryFiles.push({
    path: file.rel,
    bytes: stat.size,
    extension: ext || "(none)",
    supported_for_docling: SUPPORTED_FOR_INGEST.has(ext),
    sha256_small_file: stat.size <= 32 * 1024 * 1024 ? sha256Maybe(file.path) : null
  });
}

const groups = groupFiles(inventoryFiles);
const groupSummaries = [...groups.entries()].sort().map(([key, group]) => {
  const bytes = group.reduce((sum, item) => sum + item.bytes, 0);
  const topConcepts = key.split("/").map(conceptFromToken).filter(Boolean);
  const supported = group.filter((item) => item.supported_for_docling).length;
  return {
    id: `raw_source_group_${safeId(key)}`,
    key,
    file_count: group.length,
    supported_for_docling_count: supported,
    total_bytes: bytes,
    extensions: extensionSummary(group).slice(0, 12),
    paths: group.map((item) => item.path),
    sample_paths: group.slice(0, 20).map((item) => item.path),
    concepts: [...new Set(["Raw Source", "Knowledge Intake", ...topConcepts])]
  };
});

const inventory = {
  schema_version: "0.1",
  kind: "raw_source_inventory",
  raw_root: rawRoot,
  generated_at: new Date().toISOString(),
  file_count: inventoryFiles.length,
  supported_for_docling_count: inventoryFiles.filter((item) => item.supported_for_docling).length,
  total_bytes: inventoryFiles.reduce((sum, item) => sum + item.bytes, 0),
  extensions: extensionSummary(inventoryFiles),
  groups: groupSummaries,
  warnings,
  policy: [
    "Raw source inventory records source existence and metadata only.",
    "Raw source contents are not copied into committed wiki cards.",
    "Docling/PDF extraction output remains candidate evidence until reviewed."
  ]
};
writeJson(inventoryPath, inventory);

const payload = readSourcePayload(sourcePath);
const byId = new Map(payload.documents.map((doc, index) => [doc.id, index]));

function upsert(doc) {
  if (byId.has(doc.id)) {
    payload.documents[byId.get(doc.id)] = { ...payload.documents[byId.get(doc.id)], ...doc };
  } else {
    byId.set(doc.id, payload.documents.length);
    payload.documents.push(doc);
  }
}

upsert({
  id: "raw_source_inventory",
  title: "Raw Source Inventory",
  url: "wiki/raw/",
  kind: "raw_source_inventory",
  publisher: "local",
  topic: "knowledge_intake",
  summary: `${inventory.file_count} raw source files are staged locally; ${inventory.supported_for_docling_count} are supported by the Docling candidate-ingest path.`,
  concepts: ["Raw Source", "Knowledge Intake", "Source Inventory", "Docling Evidence"],
  claims: inventory.policy,
  relationships: [
    ["Raw Source", "feeds", "Knowledge Intake"],
    ["Knowledge Intake", "feeds", "Design Strategy"],
    ["Docling Evidence", "supports", "Source Review"]
  ],
  inventory_path: inventoryPath
});

for (const group of groupSummaries) {
  upsert({
    id: group.id,
    title: `Raw Source Group: ${group.key}`,
    url: `wiki/raw/${group.key}`,
    kind: "raw_source_group",
    publisher: "local",
    topic: "knowledge_intake",
    summary: `${group.file_count} file(s), ${group.supported_for_docling_count} Docling-supported, ${group.total_bytes} bytes. Top extensions: ${group.extensions.map((item) => `${item.extension}:${item.count}`).join(", ")}.`,
    concepts: group.concepts,
    claims: [
      "This record is source metadata only; contents must be extracted and reviewed before they can drive strategy or compliance.",
      ...group.sample_paths.slice(0, 5).map((sample) => `Sample staged source: ${sample}`)
    ],
    relationships: [
      ["Raw Source", "contains", group.key],
      [group.key, "feeds", "Knowledge Intake"],
      ["Knowledge Intake", "feeds", "Design Strategy"]
    ],
    file_count: group.file_count,
    supported_for_docling_count: group.supported_for_docling_count,
    inventory_path: inventoryPath
  });
}

const community = {
  id: "community_raw_sources",
  label: "Raw Sources",
  summary: "Local ignored source inventory staged for evidence extraction, Docling conversion, and typed-card promotion.",
  members: ["Raw Source", "Source Inventory", "Knowledge Intake", "Docling Evidence", "Source Review"]
};
const existingCommunity = payload.communities.find((item) => item.id === community.id);
if (existingCommunity) {
  existingCommunity.summary = community.summary;
  for (const member of community.members) {
    if (!existingCommunity.members.includes(member)) existingCommunity.members.push(member);
  }
} else {
  payload.communities.push(community);
}

writeJson(sourcePath, payload);
console.log(JSON.stringify({
  raw_root: rawRoot,
  inventory: inventoryPath,
  file_count: inventory.file_count,
  supported_for_docling_count: inventory.supported_for_docling_count,
  group_count: groupSummaries.length,
  warning_count: warnings.length
}, null, 2));
