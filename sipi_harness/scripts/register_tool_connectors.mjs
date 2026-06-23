import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readJsonOrNull, readSourcePayload, writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const connectorPath = path.join(root, "data", "tool_connectors.json");
const sourcePath = path.join(root, "data", "sources.json");

const connectorPayload = readJsonOrNull(connectorPath) || { connectors: [] };
const sourcePayload = readSourcePayload(sourcePath);
const existingIds = new Set(sourcePayload.documents.map((doc) => doc.id));

let added = 0;
for (const connector of connectorPayload.connectors || []) {
  const docId = `doc_${connector.id}`;
  if (existingIds.has(docId)) continue;
  sourcePayload.documents.push({
    id: docId,
    title: connector.title,
    url: connector.url,
    kind: connector.kind,
    summary: connector.summary,
    concepts: connector.concepts,
    claims: connector.claims,
    relationships: connector.relationships
  });
  added += 1;
}

let community = sourcePayload.communities.find((item) => item.id === "community_tool_connectors");
if (!community) {
  community = {
    id: "community_tool_connectors",
    title: "Tool Connectors",
    summary: "MCP and skill connectors that turn wiki/spec knowledge into design, simulation, and analysis actions.",
    members: ["KiCAD MCP", "PyAEDT", "Keysight ADS", "PCB Design Tool", "Analysis Evidence"]
  };
  sourcePayload.communities.push(community);
}

writeJson(sourcePath, sourcePayload);
console.log(`Registered ${added} tool connector source(s) in ${sourcePath}.`);
