import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(root, "data", "sources.json");
const dataDir = path.join(root, "data");

const strategyPayloads = fs
  .readdirSync(dataDir)
  .filter((name) => /^design_strategy_sources.*\.json$/.test(name))
  .sort()
  .map((name) => JSON.parse(fs.readFileSync(path.join(dataDir, name), "utf8")));
const sourcePayload = readSourcePayload(sourcePath);
const existingIds = new Set(sourcePayload.documents.map((doc) => doc.id));

let added = 0;
for (const strategy of strategyPayloads.flatMap((payload) => payload.strategy_sources || [])) {
  const docId = `doc_${strategy.id}`;
  if (existingIds.has(docId)) continue;

  const concepts = [
    ...strategy.concepts,
    "Design Strategy",
    "Design Rule",
    "Verification Method",
    ...strategy.design_rules,
    ...strategy.verification
  ];

  const relationships = [
    ...strategy.relationships,
    [strategy.title, "provides", "Design Strategy"],
    ["Design Strategy", "generates", "Design Rule"],
    ["Design Rule", "is checked by", "Verification Method"]
  ];

  sourcePayload.documents.push({
    id: docId,
    title: strategy.title,
    url: strategy.url,
    kind: "design_strategy",
    publisher: strategy.publisher,
    topic: strategy.topic,
    summary: strategy.summary,
    concepts: [...new Set(concepts)],
    claims: strategy.claims,
    relationships
  });
  added += 1;
}

for (const strategyCommunity of strategyPayloads.flatMap((payload) => payload.strategy_communities || [])) {
  const existing = sourcePayload.communities.find((community) => community.id === strategyCommunity.id);
  if (existing) {
    existing.summary = strategyCommunity.summary;
    for (const member of strategyCommunity.members) {
      if (!existing.members.includes(member)) existing.members.push(member);
    }
  } else {
    sourcePayload.communities.push(strategyCommunity);
  }
}

writeJson(sourcePath, sourcePayload);
console.log(`Registered ${added} new design strategy source(s) in ${sourcePath}.`);
