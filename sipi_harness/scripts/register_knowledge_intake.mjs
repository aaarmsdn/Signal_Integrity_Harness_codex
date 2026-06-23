import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(root, "data", "sources.json");
const intakeRoot = path.join(root, "knowledge_intake");

function readJsonOrNull(filePath) {
  if (!fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function slug(value) {
  return String(value || "source")
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 96) || "source";
}

function collectJsonFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const filePath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectJsonFiles(filePath));
    } else if (entry.isFile() && entry.name.endsWith(".json")) {
      results.push(filePath);
    }
  }
  return results.sort();
}

function normalizeSource(item, fallbackKind) {
  const title = item.title || item.name || item.url || item.path || item.id;
  if (!title) return null;
  const concepts = [
    ...(item.concepts || []),
    ...(item.keywords || []),
    fallbackKind === "web_research" ? "Web Research" : "User Reference",
    "Design Strategy"
  ];
  const claims = [
    ...(item.claims || []),
    ...(item.design_rules || []),
    ...(item.verification_methods || [])
  ].filter(Boolean);
  const relationships = [
    ...(item.relationships || []),
    [title, "supports", "Design Strategy"]
  ];
  return {
    id: `knowledge_${slug(item.id || title)}`,
    title,
    url: item.url || item.path || "",
    kind: fallbackKind,
    publisher: item.publisher || item.organization || "",
    topic: item.topic || "design_strategy",
    summary: item.summary || item.notes || "",
    concepts: [...new Set(concepts.filter(Boolean))],
    claims,
    relationships
  };
}

function registryDocuments(registry, fallbackKind) {
  const sourceItems = [
    ...(registry.sources || []),
    ...(registry.references || []),
    ...(registry.documents || [])
  ];
  return sourceItems.map((item) => normalizeSource(item, fallbackKind)).filter(Boolean);
}

const payload = readSourcePayload(sourcePath);
const existingIds = new Set(payload.documents.map((doc) => doc.id));
let added = 0;

for (const filePath of collectJsonFiles(intakeRoot)) {
  const registry = readJsonOrNull(filePath);
  if (!registry || typeof registry !== "object") continue;
  const kind = registry.kind === "user_reference_registry" ? "user_reference" : "web_research";
  for (const doc of registryDocuments(registry, kind)) {
    if (existingIds.has(doc.id)) continue;
    payload.documents.push(doc);
    existingIds.add(doc.id);
    added += 1;
  }
}

const communities = [
  {
    id: "community_knowledge_intake",
    label: "Knowledge Intake",
    summary: "Web research and user-provided references collected before design strategy generation.",
    members: ["Knowledge Intake", "Web Research", "User Reference", "Design Strategy", "Evidence"]
  }
];

for (const community of communities) {
  const existing = payload.communities.find((item) => item.id === community.id);
  if (!existing) payload.communities.push(community);
}

writeJson(sourcePath, payload);
console.log(`Registered ${added} knowledge intake source(s) from ${intakeRoot}.`);
