import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readJsonOrNull, readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const formulaPath = path.join(root, "data", "formula_sources.json");
const sourcePath = path.join(root, "data", "sources.json");

const formulaPayload = readJsonOrNull(formulaPath) || { formula_sources: [], formula_communities: [] };
const sourcePayload = readSourcePayload(sourcePath);
const existingIds = new Set(sourcePayload.documents.map((doc) => doc.id));

let added = 0;
for (const item of formulaPayload.formula_sources || []) {
  const docId = `doc_${item.id}`;
  if (existingIds.has(docId)) continue;

  const concepts = [
    item.title,
    "Formula",
    "First-Pass Estimate",
    "Sanity Check",
    "Verification Method",
    ...item.concepts,
    ...item.design_use,
    ...item.caveats
  ];

  const relationships = [
    ...item.relationships,
    [item.title, "is", "Formula"],
    ["Formula", "supports", "First-Pass Estimate"],
    ["Formula", "supports", "Sanity Check"],
    ["Sanity Check", "guides", "Verification Method"]
  ];

  sourcePayload.documents.push({
    id: docId,
    title: item.title,
    url: item.url,
    kind: "formula",
    publisher: item.publisher,
    topic: item.topic,
    summary: `${item.summary} Formula: ${item.formula}`,
    formula: item.formula,
    variables: item.variables,
    units: item.units,
    concepts: [...new Set(concepts)],
    claims: [
      item.summary,
      ...item.design_use.map((use) => `Design use: ${use}`),
      ...item.caveats.map((caveat) => `Caveat: ${caveat}`)
    ],
    relationships
  });
  added += 1;
}

for (const formulaCommunity of formulaPayload.formula_communities || []) {
  const existing = sourcePayload.communities.find((community) => community.id === formulaCommunity.id);
  if (existing) {
    existing.summary = formulaCommunity.summary;
    for (const member of formulaCommunity.members) {
      if (!existing.members.includes(member)) existing.members.push(member);
    }
  } else {
    sourcePayload.communities.push(formulaCommunity);
  }
}

writeJson(sourcePath, sourcePayload);
console.log(`Registered ${added} formula source(s) in ${sourcePath}.`);
