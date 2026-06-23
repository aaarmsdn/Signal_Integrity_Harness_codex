import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(root, "data", "sources.json");

function parseArgs(argv) {
  const args = { roots: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--root" && argv[i + 1]) {
      args.roots.push(argv[++i]);
    } else if (item === "--case-dir" && argv[i + 1]) {
      args.caseDir = argv[++i];
    }
  }
  return args;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function safeId(value) {
  return String(value || "docling_source")
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 120) || "docling_source";
}

function collectFiles(dir, predicate) {
  if (!fs.existsSync(dir)) return [];
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const filePath = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...collectFiles(filePath, predicate));
    else if (entry.isFile() && predicate(filePath)) out.push(filePath);
  }
  return out.sort();
}

function defaultRoots(args) {
  const roots = [
    path.join(root, "wiki", "raw", "extracted_evidence", "docling"),
    path.join(root, "knowledge_intake", "processed", "docling")
  ];
  if (args.caseDir) roots.push(path.join(path.resolve(args.caseDir), "knowledge_intake", "processed", "docling"));
  for (const item of args.roots) roots.push(path.resolve(item));
  return [...new Set(roots)];
}

function chunkConcepts(chunk) {
  const concepts = new Set(["Docling Evidence", "Source Chunk"]);
  if (chunk.heading) concepts.add(chunk.heading);
  if (chunk.chunk_type) concepts.add(String(chunk.chunk_type).replace(/_/g, " "));
  for (const topic of chunk.topics || []) concepts.add(topic);
  const text = String(chunk.text || "").toLowerCase();
  const detectors = [
    ["impedance", "Impedance"],
    ["insertion loss", "Insertion Loss"],
    ["return loss", "Return Loss"],
    ["crosstalk", "Crosstalk"],
    ["skew", "Skew"],
    ["jitter", "Jitter"],
    ["eye", "Eye Diagram"],
    ["ber", "BER"],
    ["bump map", "Bump Map"],
    ["ball map", "Ball Map"],
    ["pin map", "Pin Map"],
    ["via", "Via Transition"],
    ["return path", "Return Path"],
    ["decap", "Decoupling"],
    ["ir drop", "IR Drop"],
    ["ssn", "SSN"]
  ];
  for (const [needle, concept] of detectors) {
    if (text.includes(needle)) concepts.add(concept);
  }
  return [...concepts].filter(Boolean);
}

function chunkRelationships(chunk, title) {
  const relationships = [[title, "contains", chunk.heading || "Source Chunk"]];
  for (const rel of chunk.relationships || []) {
    if (Array.isArray(rel) && rel.length === 3) relationships.push(rel);
    else if (rel && typeof rel === "object" && rel.source && rel.predicate && rel.target) {
      relationships.push([rel.source, rel.predicate, rel.target]);
    }
  }
  return relationships;
}

function summaryToDoc(summary, manifestPath) {
  const sourceId = summary.source_id || safeId(summary.title || summary.source);
  return {
    id: `docling_source_${safeId(sourceId)}`,
    title: summary.title || sourceId,
    url: summary.source || summary.markdown || "",
    kind: "docling_source",
    publisher: "docling",
    topic: "design_strategy",
    summary: `Docling candidate source. Review status: ${summary.review_status || "unreviewed"}.`,
    concepts: ["Docling Evidence", "Source Document"],
    claims: [
      "Docling output is candidate evidence and must be reviewed before promotion to design rules or compliance thresholds."
    ],
    relationships: [["Source Document", "is converted into", "Docling Evidence"]],
    source_manifest: manifestPath,
    source_tier: summary.source_tier || "tier_1"
  };
}

function chunkToDoc(chunk, manifestPath) {
  const id = `docling_chunk_${safeId(chunk.chunk_id || `${chunk.source_id}_${chunk.heading}`)}`;
  const title = `${chunk.title || chunk.source_id || "Docling Source"} - ${chunk.heading || chunk.chunk_type || "Chunk"}`;
  const text = String(chunk.text || "").replace(/\s+/g, " ").trim();
  return {
    id,
    title,
    url: chunk.source || "",
    kind: "docling_chunk",
    publisher: "docling",
    topic: chunk.topics?.[0] || "design_strategy",
    summary: text.slice(0, 360),
    concepts: chunkConcepts(chunk),
    claims: text ? [text.slice(0, 900)] : [],
    relationships: chunkRelationships(chunk, chunk.title || "Source Document"),
    source_manifest: manifestPath,
    source_id: chunk.source_id,
    chunk_id: chunk.chunk_id,
    source_tier: chunk.source_tier || "tier_1",
    review_status: chunk.review_status || "unreviewed",
    evidence_status: chunk.evidence_status || "candidate"
  };
}

function resolveFromManifest(filePath, manifestPath) {
  if (!filePath) return "";
  if (path.isAbsolute(filePath)) return filePath;
  return path.resolve(path.dirname(manifestPath), filePath);
}

const args = parseArgs(process.argv.slice(2));
const payload = readSourcePayload(sourcePath);
const existing = new Set(payload.documents.map((doc) => doc.id));
let added = 0;

for (const rootDir of defaultRoots(args)) {
  const manifests = collectFiles(rootDir, (filePath) => path.basename(filePath) === "docling_ingest_manifest.json");
  for (const manifestPath of manifests) {
    const manifest = readJson(manifestPath);
    for (const summary of manifest.items || []) {
      const doc = summaryToDoc(summary, manifestPath);
      if (!existing.has(doc.id)) {
        payload.documents.push(doc);
        existing.add(doc.id);
        added += 1;
      }
      const chunksPath = resolveFromManifest(summary.chunks, manifestPath);
      if (!chunksPath || !fs.existsSync(chunksPath)) continue;
      const chunks = readJson(chunksPath);
      for (const chunk of chunks) {
        const chunkDoc = chunkToDoc(chunk, manifestPath);
        if (existing.has(chunkDoc.id)) continue;
        payload.documents.push(chunkDoc);
        existing.add(chunkDoc.id);
        added += 1;
      }
    }
  }
}

const community = {
  id: "community_docling_evidence",
  label: "Docling Evidence",
  summary: "Layout-aware source chunks converted by Docling and awaiting review/promotion.",
  members: ["Docling Evidence", "Source Document", "Source Chunk", "Table Candidate", "Figure Candidate", "Equation Candidate"]
};
if (!payload.communities.some((item) => item.id === community.id)) payload.communities.push(community);

writeJson(sourcePath, payload);
console.log(`Registered ${added} Docling source/chunk document(s).`);
