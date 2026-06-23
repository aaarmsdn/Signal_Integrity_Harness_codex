import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { asArray, isGraphPage, readWikiPages } from "./wiki_utils.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const graphPath = path.join(root, "data", "knowledge_graph.json");
const wikiDir = path.join(root, "wiki");
const vaultRoot = path.join(root, "obsidian_vault");
const maxClaimChars = 900;
const maxChunkChars = 1800;

const graph = JSON.parse(fs.readFileSync(graphPath, "utf8"));
const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
const docsById = new Map(graph.documents.map((doc) => [doc.id, doc]));

function resetDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

function safeName(value, fallback = "untitled") {
  return String(value || fallback)
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function mdEscape(value) {
  return String(value || "").replace(/\r/g, "").trim();
}

function wiki(label) {
  return `[[${safeName(label)}]]`;
}

function isUsefulConceptLabel(label) {
  const value = String(label || "").trim();
  if (!value) return false;
  if (value.length > 64) return false;
  if (/[.!?]$/.test(value)) return false;
  if (/^(Design use|Caveat):/i.test(value)) return false;
  return true;
}

function tag(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function frontmatter(entries) {
  const lines = ["---"];
  for (const [key, value] of Object.entries(entries)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      lines.push(`${key}:`);
      for (const item of value) lines.push(`  - ${JSON.stringify(String(item))}`);
    } else {
      lines.push(`${key}: ${JSON.stringify(String(value))}`);
    }
  }
  lines.push("---", "");
  return lines.join("\n");
}

function writeNote(folder, title, body) {
  const dir = path.join(vaultRoot, folder);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, `${safeName(title)}.md`), body, "utf8");
}

function backlinksForDoc(docId) {
  const links = graph.links.filter((link) => link.documents?.includes(docId));
  const related = new Set();
  for (const link of links) {
    const source = nodeById.get(link.source);
    const target = nodeById.get(link.target);
    if (source?.type === "concept" && isUsefulConceptLabel(source.label)) related.add(source.label);
    if (target?.type === "concept" && isUsefulConceptLabel(target.label)) related.add(target.label);
  }
  return [...related].sort();
}

function sourceUrl(doc) {
  if (!doc.url) return "";
  return doc.url.startsWith("local://") ? "" : doc.url;
}

function isSourceLikeDoc(doc) {
  const kind = String(doc?.kind || "").toLowerCase();
  return [
    "book_chunk",
    "book_reference",
    "sipi_reference",
    "local_design",
    "llm_wiki_method",
    "specification",
    "tool_connector",
    "web_research",
    "user_reference"
  ].includes(kind);
}

function sourceNoteLine(doc) {
  if (!doc) return "";
  return isSourceLikeDoc(doc) ? `- ${safeName(doc.title)} \`${doc.id}\`` : `- ${wiki(doc.title)}`;
}

function bodyWithoutFrontmatter(text) {
  return String(text || "").replace(/^---[\s\S]*?---\s*/m, "").trim();
}

function typedCardFolder(pageType) {
  const label = String(pageType || "other")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
  return path.join("20_Typed_Wiki_Cards", safeName(label));
}

function pageId(page) {
  return page?.meta?.id || page?.name?.replace(/\.md$/i, "");
}

function relationshipLinks(relationships) {
  return asArray(relationships)
    .map((item) => {
      if (typeof item === "string") {
        const [source, predicate, target] = item.split("|").map((part) => part.trim());
        return source && predicate && target ? { source, predicate, target, polarity: "" } : null;
      }
      if (item && typeof item === "object" && item.source && item.predicate && item.target) return item;
      return null;
    })
    .filter(Boolean)
    .map((item) => {
      const polarity = item.polarity ? ` / ${item.polarity}` : "";
      return `- ${wiki(item.source)} -- ${item.predicate}${polarity} --> ${wiki(item.target)}`;
    });
}

function scoreRelatedCards(page, candidate) {
  if (page.name === candidate.name) return 0;
  const aTopics = new Set(asArray(page.meta.topics));
  const bTopics = new Set(asArray(candidate.meta.topics));
  const aStages = new Set(asArray(page.meta.design_stage));
  const bStages = new Set(asArray(candidate.meta.design_stage));
  const aOutputs = new Set(asArray(page.meta.outputs_to));
  const bOutputs = new Set(asArray(candidate.meta.outputs_to));
  let score = 0;
  for (const topic of aTopics) if (bTopics.has(topic)) score += 3;
  for (const stage of aStages) if (bStages.has(stage)) score += 1;
  for (const output of aOutputs) if (bOutputs.has(output)) score += 2;
  if (page.meta.page_type && page.meta.page_type === candidate.meta.page_type) score += 1;
  return score;
}

function writeTypedWikiCards() {
  if (!fs.existsSync(wikiDir)) return;
  const pages = readWikiPages(wikiDir)
    .filter((page) => !page.name.replace(/\\/g, "/").startsWith("raw/"))
    .filter((page) => !page.isControl && isGraphPage(page.meta));
  const titleById = new Map(pages.map((page) => [pageId(page), page.title]));
  for (const page of pages.sort((a, b) => a.name.localeCompare(b.name))) {
    if (page.isControl || !isGraphPage(page.meta)) continue;
    const meta = page.meta || {};
    const pageType = meta.page_type || "wiki_card";
    const sourceCard = pageType === "source_card";
    const tags = [
      "sipi",
      "typed-wiki-card",
      pageType,
      ...asArray(meta.domain),
      ...asArray(meta.interfaces),
      ...asArray(meta.topics),
      ...asArray(meta.design_stage)
    ].filter(Boolean).map(tag);
    const relationshipLines = relationshipLinks(meta.relationships);
    const relationshipConcepts = asArray(meta.relationships).flatMap((item) => {
      if (typeof item === "string") {
        const [source, , target] = item.split("|").map((part) => part.trim());
        return [source, target].filter(Boolean);
      }
      return item && typeof item === "object" ? [item.source, item.target].filter(Boolean) : [];
    });
    const conceptLinks = [...new Set([...asArray(meta.concepts), ...relationshipConcepts])]
      .filter(isUsefulConceptLabel)
      .sort()
      .map((concept) => `- ${wiki(concept)}`)
      .join("\n");
    const conceptText = [...new Set([...asArray(meta.concepts), ...relationshipConcepts])]
      .filter(isUsefulConceptLabel)
      .sort()
      .map((concept) => `- ${concept}`)
      .join("\n");
    const topicLinks = asArray(meta.topics)
      .sort()
      .map((topicName) => `- ${wiki(topicName)}`)
      .join("\n");
    const sourceRefs = asArray(meta.source_ids)
      .map((source) => {
        const title = titleById.get(source);
        return title ? `- \`${source}\` (${wiki(title)})` : `- \`${source}\``;
      })
      .join("\n");
    const relatedCards = pages
      .map((candidate) => ({ page: candidate, score: scoreRelatedCards(page, candidate) }))
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score || a.page.title.localeCompare(b.page.title))
      .slice(0, 10)
      .map((item) => `- ${wiki(item.page.title)} _score ${item.score}_`)
      .join("\n");
    const outputs = asArray(meta.outputs_to).map((item) => `- \`${item}\``).join("\n");
    const missing = asArray(meta.missing_information).map((item) => `- ${mdEscape(item)}`).join("\n");
    const body =
      frontmatter({
        id: meta.id,
        type: pageType,
        page_type: pageType,
        source_tier: meta.source_tier,
        confidence: meta.confidence,
        status: meta.status,
        wiki_path: page.name
      }) +
      `# ${page.title}\n\n` +
      `#${tags.join(" #")}\n\n` +
      `## Retrieval Metadata\n\n` +
      `- Page type: \`${pageType}\`\n` +
      `- Source tier: \`${meta.source_tier || "missing"}\`\n` +
      `- Status: \`${meta.status || "missing"}\`\n` +
      `- Confidence: \`${meta.confidence || "missing"}\`\n` +
      `- Wiki path: \`${page.name}\`\n\n` +
      `${outputs ? `## Outputs To\n\n${outputs}\n\n` : ""}` +
      `${sourceCard && conceptText ? `## Indexed Concepts\n\n${conceptText}\n\n` : ""}` +
      `${!sourceCard && conceptLinks ? `## Concept Links\n\n${conceptLinks}\n\n` : ""}` +
      `${!sourceCard && relationshipLines.length ? `## Engineering Relationships\n\n${relationshipLines.join("\n")}\n\n` : ""}` +
      `${topicLinks ? `## Topic Links\n\n${topicLinks}\n\n` : ""}` +
      `${relatedCards ? `## Related Typed Cards\n\n${relatedCards}\n\n` : ""}` +
      `${sourceRefs ? `## Source IDs\n\n${sourceRefs}\n\n` : ""}` +
      `${missing ? `## Missing Information\n\n${missing}\n\n` : ""}` +
      `## Card Body\n\n${bodyWithoutFrontmatter(page.text)}\n`;
    writeNote(typedCardFolder(pageType), page.title, body);
  }
}

resetDir(vaultRoot);
fs.mkdirSync(path.join(vaultRoot, ".obsidian"), { recursive: true });
fs.writeFileSync(
  path.join(vaultRoot, ".obsidian", "graph.json"),
  JSON.stringify(
    {
      "collapse-filter": false,
      search: "",
      showTags: true,
      showAttachments: false,
      hideUnresolved: false,
      showOrphans: false,
      "collapse-color-groups": false
    },
    null,
    2
  ),
  "utf8"
);

const kindToFolder = {
  formula: "01_Formulas",
  design_strategy: "02_Design_Strategies",
  specification: "03_Specifications",
  sipi_reference: "06_References",
  local_design: "06_References",
  llm_wiki_method: "06_References"
};

for (const doc of graph.documents) {
  if (doc.kind === "wiki") continue;
  const folder = kindToFolder[doc.kind] || "06_References";
  const related = backlinksForDoc(doc.id);
  const tags = ["sipi", doc.kind, doc.topic, doc.publisher].filter(Boolean).map(tag);
  const title = doc.title;
  const source = sourceUrl(doc);
  const formulaSection = doc.formula
    ? `## Formula\n\n\`${doc.formula}\`\n\n${doc.variables ? `## Variables\n\n${Object.entries(doc.variables).map(([key, value]) => `- \`${key}\`: ${value}`).join("\n")}\n\n` : ""}`
    : "";

  const body =
    frontmatter({
      id: doc.id,
      kind: doc.kind,
      topic: doc.topic,
      publisher: doc.publisher,
      source
    }) +
    `# ${title}\n\n` +
    `#${tags.join(" #")}\n\n` +
    `${doc.summary ? `## Summary\n\n${mdEscape(doc.summary)}\n\n` : ""}` +
    formulaSection +
    `${doc.claims?.length ? `## Claims\n\n${doc.claims.map((claim) => `- ${mdEscape(claim).slice(0, maxClaimChars)}`).join("\n")}\n\n` : ""}` +
    `${related.length && !isSourceLikeDoc(doc) ? `## Related Concepts\n\n${related.slice(0, 60).map((label) => `- ${wiki(label)}`).join("\n")}\n\n` : ""}` +
    `${related.length && isSourceLikeDoc(doc) ? `## Indexed Concepts\n\n${related.slice(0, 60).map((label) => `- ${label}`).join("\n")}\n\n` : ""}` +
    `${source ? `## Source\n\n${source}\n` : ""}`;
  writeNote(folder, title, body);
}

const conceptDocs = new Map();
for (const node of graph.nodes.filter((node) => node.type === "concept" && isUsefulConceptLabel(node.label))) {
  conceptDocs.set(node.id, node.documents?.map((docId) => docsById.get(docId)).filter(Boolean) || []);
}

for (const node of graph.nodes.filter((node) => node.type === "concept")) {
  const neighborhood = graph.links
    .filter((link) => link.source === node.id || link.target === node.id)
    .slice(0, 120)
    .map((link) => {
      const otherId = link.source === node.id ? link.target : link.source;
      const other = nodeById.get(otherId);
      return other && isUsefulConceptLabel(other.label) ? `- ${link.source === node.id ? link.predicate : `< ${link.predicate}`} ${wiki(other.label)}` : null;
    })
    .filter(Boolean);
  const docs = conceptDocs.get(node.id) || [];
  const linkedDocs = docs.filter((doc) => !isSourceLikeDoc(doc));
  const evidenceDocs = docs.filter(isSourceLikeDoc);
  const body =
    frontmatter({
      id: node.id,
      kind: "concept",
      community: node.community,
      weight: node.weight
    }) +
    `# ${node.label}\n\n` +
    `#sipi #concept\n\n` +
    `${node.claims?.length ? `## Claims\n\n${node.claims.map((claim) => `- ${mdEscape(claim).slice(0, maxClaimChars)}`).join("\n")}\n\n` : ""}` +
    `${neighborhood.length ? `## Graph Links\n\n${neighborhood.join("\n")}\n\n` : ""}` +
    `${linkedDocs.length ? `## Related Cards\n\n${linkedDocs.slice(0, 80).map(sourceNoteLine).join("\n")}\n\n` : ""}` +
    `${evidenceDocs.length ? `## Evidence Sources\n\n${evidenceDocs.slice(0, 80).map(sourceNoteLine).join("\n")}\n` : ""}`;
  writeNote("00_Concepts", node.label, body);
}

const topicGroups = new Map();
for (const doc of graph.documents) {
  if (!doc.topic) continue;
  if (!topicGroups.has(doc.topic)) topicGroups.set(doc.topic, []);
  topicGroups.get(doc.topic).push(doc);
}

for (const [topicName, docs] of [...topicGroups.entries()].sort()) {
  const body =
    frontmatter({ kind: "topic_index", topic: topicName }) +
    `# ${topicName}\n\n#sipi #topic-index\n\n` +
    docs
      .sort((a, b) => safeName(a.title).localeCompare(safeName(b.title)))
      .map((doc) => `- ${wiki(doc.title)} ${doc.kind ? `#${tag(doc.kind)}` : ""}`)
      .join("\n") +
    "\n";
  writeNote("10_Topic_Indexes", topicName, body);
}

writeTypedWikiCards();

const home =
  frontmatter({ kind: "home" }) +
  `# SI PI LLM Wiki Vault\n\n` +
  `Generated from \`sipi_harness/data/knowledge_graph.json\`.\n\n` +
  `## Start Here\n\n` +
  `- [[Typed Wiki Cards]]\n` +
  `- [[Target Impedance]]\n` +
  `- [[Decoupling Capacitor]]\n` +
  `- [[Microstrip Line]]\n` +
  `- [[Crosstalk]]\n` +
  `- [[SSN]]\n` +
  `- [[IR Drop]]\n` +
  `- [[Return Path]]\n\n` +
  `## Counts\n\n` +
  `- Documents: ${graph.documents.length}\n` +
  `- Concepts: ${graph.nodes.filter((node) => node.type === "concept").length}\n` +
  `- Links: ${graph.links.length}\n` +
  `- Typed wiki cards: ${readWikiPages(wikiDir).filter((page) => !page.name.replace(/\\/g, "/").startsWith("raw/")).filter((page) => !page.isControl && isGraphPage(page.meta)).length}\n`;

fs.writeFileSync(path.join(vaultRoot, "Home.md"), home, "utf8");

const typedIndex =
  frontmatter({ kind: "typed_wiki_cards_index" }) +
  `# Typed Wiki Cards\n\n#sipi #typed-wiki-card #index\n\n` +
  `These notes mirror \`sipi_harness/wiki/\` graph cards for Obsidian browsing. The SIPI-native markdown files remain the source of truth.\n\n` +
  [...new Set(readWikiPages(wikiDir).filter((page) => !page.name.replace(/\\/g, "/").startsWith("raw/")).filter((page) => !page.isControl && isGraphPage(page.meta)).map((page) => page.meta.page_type || "wiki_card"))]
    .sort()
    .map((pageType) => `- [[${safeName(String(pageType).replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()))}]]`)
    .join("\n") +
  "\n";
writeNote("20_Typed_Wiki_Cards", "Typed Wiki Cards", typedIndex);

console.log(`Exported Obsidian vault to ${vaultRoot}`);
