import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readSourcePayload, writeJson } from "./graph_io.mjs";
import { asArray, isGraphPage, markdownTitle, readWikiPages, slug } from "./wiki_utils.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(root, "data", "sources.json");
const graphPath = path.join(root, "data", "knowledge_graph.json");
const graphDataJsPath = path.join(root, "app", "graph-data.js");
const wikiDir = path.join(root, "wiki");

function addToMapSet(map, key, value) {
  if (!map.has(key)) map.set(key, new Set());
  map.get(key).add(value);
}

function addToMapList(map, key, value) {
  if (!map.has(key)) map.set(key, []);
  map.get(key).push(value);
}

const payload = readSourcePayload(sourcePath);
const documents = payload.documents;
const communities = payload.communities || [];

function addWikiDocuments() {
  if (!fs.existsSync(wikiDir)) return;
  const existing = new Set(documents.map((doc) => doc.id));
  for (const page of readWikiPages(wikiDir)
    .filter((item) => !item.name.replace(/\\/g, "/").startsWith("raw/"))
    .sort((a, b) => a.name.localeCompare(b.name))) {
    const { name, text, meta } = page;
    if (page.isControl || !meta || !isGraphPage(meta)) continue;
    const id = meta.id || `wiki_${slug(name.replace(/\.md$/i, ""))}`;
    if (existing.has(id)) continue;
    const concepts = [...new Set([...asArray(meta.concepts), markdownTitle(name, text)])];
    const relationships = asArray(meta.relationships)
      .map((item) => {
        if (typeof item === "string") return item.split("|").map((part) => part.trim());
        if (item && typeof item === "object" && item.source && item.predicate && item.target) {
          return [item.source, item.predicate, item.target];
        }
        return null;
      })
      .filter((parts) => Array.isArray(parts) && parts.length === 3);
    const claims = asArray(meta.claims)
      .map((claim) => (typeof claim === "string" ? claim : claim?.text || claim?.id || ""))
      .filter(Boolean);
    const bodySummary = text
      .replace(/^---[\s\S]*?---\s*/m, "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#") && !line.startsWith("- ") && !line.startsWith("```"))[0] || "";
    documents.push({
      id,
      title: markdownTitle(name, text),
      url: `wiki/${name}`,
      kind: "wiki",
      topic: asArray(meta.topics)[0] || meta.topic || meta.page_type || "design_strategy",
      summary: meta.summary || bodySummary,
      concepts,
      claims,
      relationships,
      source_refs: asArray(meta.source_ids).length ? asArray(meta.source_ids) : asArray(meta.sources),
      page_type: meta.page_type || null,
      domain: asArray(meta.domain),
      topics: asArray(meta.topics),
      design_stage: asArray(meta.design_stage),
      source_tier: meta.source_tier || null,
      outputs_to: asArray(meta.outputs_to),
      interfaces: asArray(meta.interfaces),
      spec_versions: asArray(meta.spec_versions),
      confidence: meta.confidence || null,
      status: meta.status || null,
      missing_information: asArray(meta.missing_information)
    });
    existing.add(id);
  }
}

function addDefaultCommunities() {
  const defaults = [
    {
      id: "community_signal_integrity",
      label: "Signal Integrity",
      summary: "Loss, impedance, reflection, return path, crosstalk, timing, and frequency/transient-domain design strategies.",
      members: ["Signal Integrity", "Insertion Loss", "Return Loss", "Crosstalk", "Impedance", "Return Path", "Eye Diagram", "Jitter"]
    },
    {
      id: "community_power_integrity",
      label: "Power Integrity",
      summary: "PDN impedance, IR drop, decoupling, SSN, rail noise, and transient response strategies.",
      members: ["Power Integrity", "PDN", "Target Impedance", "IR Drop", "Decoupling", "SSN", "Ground Bounce", "Rail Noise"]
    },
    {
      id: "community_package_pcb",
      label: "Package and PCB",
      summary: "Stackup, launch, via, pad, escape routing, length matching, and geometry gates.",
      members: ["Package", "PCB", "Stackup", "Via", "Pad", "Launch", "Length Matching", "Geometry Gate"]
    },
    {
      id: "community_verification_strategy",
      label: "Verification Strategy",
      summary: "EM extraction, Nyquist coverage, Touchstone, ADS checks, masks, and report evidence.",
      members: ["Verification Method", "EM Extraction", "HFSS 3D Layout", "Touchstone", "ADS", "Nyquist Frequency", "Design Strategy"]
    }
  ];
  for (const item of defaults) {
    const existing = communities.find((community) => community.id === item.id);
    if (!existing) communities.push(item);
  }
}

addWikiDocuments();
addDefaultCommunities();

const conceptDocs = new Map();
const conceptClaims = new Map();
const relationCounter = new Map();
const relationDocs = new Map();

for (const doc of documents) {
  const concepts = doc.concepts || [];
  for (const concept of concepts) {
    addToMapSet(conceptDocs, concept, doc.id);
  }

  for (const claim of doc.claims || []) {
    const lowered = String(claim).toLowerCase();
    for (const concept of concepts) {
      if (lowered.includes(concept.toLowerCase()) || concepts.length <= 6) {
        addToMapList(conceptClaims, concept, claim);
      }
    }
  }

  for (const [source, predicate, target] of doc.relationships || []) {
    const key = JSON.stringify([source, predicate, target]);
    relationCounter.set(key, (relationCounter.get(key) || 0) + 1);
    addToMapSet(relationDocs, key, doc.id);
    addToMapSet(conceptDocs, source, doc.id);
    addToMapSet(conceptDocs, target, doc.id);
  }
}

const communityByMember = new Map();
for (const community of communities) {
  for (const member of community.members || []) {
    communityByMember.set(member, community.id);
  }
}

const nodes = [...conceptDocs.keys()].sort().map((concept) => {
  const docs = [...conceptDocs.get(concept)].sort();
  return {
    id: slug(concept),
    label: concept,
    type: "concept",
    community: communityByMember.get(concept) || "community_uncategorized",
    weight: docs.length,
    documents: docs,
    claims: (conceptClaims.get(concept) || []).slice(0, 6)
  };
});

for (const doc of documents) {
  nodes.push({
    id: doc.id,
    label: doc.title,
    type: "document",
    community: "community_sources",
    weight: 1,
    url: doc.url,
    summary: doc.summary,
    kind: doc.kind
  });
}

const links = [];
for (const [key, weight] of [...relationCounter.entries()].sort()) {
  const [source, predicate, target] = JSON.parse(key);
  links.push({
    source: slug(source),
    target: slug(target),
    predicate,
    weight: weight * 3,
    signal_weight: weight * 3,
    signals: {
      direct_link: weight,
      source_overlap: 0,
      adamic_adar: 0,
      type_affinity: 0
    },
    documents: [...relationDocs.get(key)].sort()
  });
}

for (const doc of documents) {
  for (const concept of doc.concepts || []) {
    links.push({
      source: doc.id,
      target: slug(concept),
      predicate: "mentions",
      weight: 1,
      signal_weight: 1,
      signals: {
        direct_link: 0,
        source_overlap: 1,
        adamic_adar: 0,
        type_affinity: 0
      },
      documents: [doc.id]
    });
  }
}

function graphInsights() {
  const degree = new Map();
  const neighborCommunities = new Map();
  const communityMembers = new Map();
  const communityEdges = new Map();
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  for (const node of nodes.filter((node) => node.type === "concept")) {
    degree.set(node.id, 0);
    neighborCommunities.set(node.id, new Set());
    if (!communityMembers.has(node.community)) communityMembers.set(node.community, new Set());
    communityMembers.get(node.community).add(node.id);
  }

  for (const link of links) {
    const source = nodeById.get(link.source);
    const target = nodeById.get(link.target);
    if (!source || !target || source.type !== "concept" || target.type !== "concept") continue;
    degree.set(source.id, (degree.get(source.id) || 0) + 1);
    degree.set(target.id, (degree.get(target.id) || 0) + 1);
    neighborCommunities.get(source.id)?.add(target.community);
    neighborCommunities.get(target.id)?.add(source.community);
    if (source.community === target.community) {
      communityEdges.set(source.community, (communityEdges.get(source.community) || 0) + 1);
    }
  }

  const isolatedConcepts = [...degree.entries()]
    .filter(([, value]) => value <= 1)
    .map(([id, value]) => ({ id, label: nodeById.get(id)?.label || id, degree: value }))
    .slice(0, 40);

  const bridgeConcepts = [...neighborCommunities.entries()]
    .map(([id, communitiesForNode]) => ({
      id,
      label: nodeById.get(id)?.label || id,
      community_count: communitiesForNode.size,
      communities: [...communitiesForNode].sort()
    }))
    .filter((item) => item.community_count >= 3)
    .sort((a, b) => b.community_count - a.community_count)
    .slice(0, 20);

  const sparseCommunities = [...communityMembers.entries()]
    .map(([community, members]) => {
      const memberCount = members.size;
      const possible = memberCount * (memberCount - 1) / 2;
      const cohesion = possible ? (communityEdges.get(community) || 0) / possible : 0;
      return { community, member_count: memberCount, cohesion: Number(cohesion.toFixed(3)) };
    })
    .filter((item) => item.member_count >= 3 && item.cohesion < 0.15)
    .sort((a, b) => a.cohesion - b.cohesion);

  return {
    isolated_concepts: isolatedConcepts,
    bridge_concepts: bridgeConcepts,
    sparse_communities: sparseCommunities
  };
}

const graph = {
  schema_version: payload.schema_version,
  generated_from: payload.generated_from,
  relevance_model: {
    direct_link: 3.0,
    source_overlap: 4.0,
    adamic_adar: 1.5,
    type_affinity: 1.0,
    note: "The current harness stores direct relationship and source/mention signals explicitly. Adamic-Adar and type affinity are reserved for future page-to-page retrieval ranking."
  },
  nodes,
  links,
  documents,
  communities,
  insights: graphInsights()
};

writeJson(graphPath, graph);
fs.writeFileSync(
  graphDataJsPath,
  `window.SIPI_GRAPH_DATA = ${JSON.stringify(graph, null, 2)};\n`,
  "utf8"
);
console.log(`Wrote ${graphPath} and ${graphDataJsPath} with ${nodes.length} nodes and ${links.length} links.`);
