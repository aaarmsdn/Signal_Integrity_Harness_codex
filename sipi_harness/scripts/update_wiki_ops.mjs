import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { asArray, isGraphPage, readWikiPages } from "./wiki_utils.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "wiki");
const graphPath = path.join(root, "data", "knowledge_graph.json");

function topicLabel(value) {
  return String(value || "uncategorized").replaceAll("_", " ");
}

function mdLink(page) {
  return `[[${page.title}]]`;
}

function pageSummary(page) {
  if (page.meta.summary) return page.meta.summary;
  const lines = page.text
    .replace(/^---[\s\S]*?---\s*/m, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && !line.startsWith("- ") && !line.startsWith("```"));
  return lines[0] || "No summary.";
}

function readGraph() {
  if (!fs.existsSync(graphPath)) return null;
  return JSON.parse(fs.readFileSync(graphPath, "utf8"));
}

function writeIndex(pages) {
  const graphPages = pages.filter((page) => !page.isControl && isGraphPage(page));
  const hubPages = pages.filter((page) => !page.isControl && !isGraphPage(page));
  const byType = new Map();
  for (const page of graphPages) {
    const pageType = page.meta.page_type || "uncategorized";
    if (!byType.has(pageType)) byType.set(pageType, []);
    byType.get(pageType).push(page);
  }

  const lines = [
    "---",
    "graph: false",
    "kind: wiki_control",
    "---",
    "",
    "# Index",
    "",
    "Content catalog for the SI/PI LLM wiki. Read this first when selecting pages for a design strategy.",
    "",
    `- Graph pages: ${graphPages.length}`,
    `- Hub pages: ${hubPages.length}`,
    `- Control pages: ${pages.filter((page) => page.isControl).length}`,
    "",
    "## Hub Pages",
    "",
    ...hubPages.sort((a, b) => a.title.localeCompare(b.title)).map((page) => `- ${mdLink(page)} - overview hub`),
    "",
  ];

  for (const [pageType, typePages] of [...byType.entries()].sort()) {
    lines.push(`## ${topicLabel(pageType)}`, "");
    for (const page of typePages.sort((a, b) => a.title.localeCompare(b.title))) {
      const topics = asArray(page.meta.topics).join(", ") || "no topics";
      const stage = asArray(page.meta.design_stage).join(", ") || "no stage";
      lines.push(`- ${mdLink(page)} - ${pageSummary(page)} _(topics: ${topics}; stage: ${stage}; tier: ${page.meta.source_tier || "none"})_`);
    }
    lines.push("");
  }

  fs.writeFileSync(path.join(wikiDir, "index.md"), `${lines.join("\n").trim()}\n`, "utf8");
}

function writeOverview(pages, graph) {
  const graphPages = pages.filter((page) => !page.isControl && isGraphPage(page));
  const topicCounts = new Map();
  const typeCounts = new Map();
  const stageCounts = new Map();
  for (const page of graphPages) {
    for (const topic of asArray(page.meta.topics).length ? asArray(page.meta.topics) : [page.meta.topic || "uncategorized"]) {
      topicCounts.set(topic, (topicCounts.get(topic) || 0) + 1);
    }
    typeCounts.set(page.meta.page_type || "uncategorized", (typeCounts.get(page.meta.page_type || "uncategorized") || 0) + 1);
    for (const stage of asArray(page.meta.design_stage)) {
      stageCounts.set(stage, (stageCounts.get(stage) || 0) + 1);
    }
  }
  const communities = graph?.communities || [];
  const insights = graph?.insights || {};

  const lines = [
    "---",
    "graph: false",
    "kind: wiki_control",
    "---",
    "",
    "# Overview",
    "",
    "Auto-generated summary of the current SI/PI LLM wiki structure.",
    "",
    "## Counts",
    "",
    `- Wiki graph pages: ${graphPages.length}`,
    `- Graph concepts: ${graph?.nodes?.filter((node) => node.type === "concept").length ?? "not built"}`,
    `- Graph documents: ${graph?.documents?.length ?? "not built"}`,
    `- Graph links: ${graph?.links?.length ?? "not built"}`,
    "",
    "## Topics",
    "",
    ...[...topicCounts.entries()].sort().map(([topic, count]) => `- ${topic}: ${count}`),
    "",
    "## Page Types",
    "",
    ...[...typeCounts.entries()].sort().map(([pageType, count]) => `- ${pageType}: ${count}`),
    "",
    "## Design Stages",
    "",
    ...[...stageCounts.entries()].sort().map(([stage, count]) => `- ${stage}: ${count}`),
    "",
    "## Communities",
    "",
    ...communities.map((community) => `- ${community.label || community.id}: ${community.summary || ""}`),
    "",
    "## Graph Health Highlights",
    "",
    `- Isolated concepts: ${insights.isolated_concepts?.length ?? "not built"}`,
    `- Bridge concepts: ${insights.bridge_concepts?.length ?? "not built"}`,
    `- Sparse communities: ${insights.sparse_communities?.length ?? "not built"}`,
    "",
    "Run `npm run lint:wiki` for a detailed health report.",
  ];

  fs.writeFileSync(path.join(wikiDir, "overview.md"), `${lines.join("\n").trim()}\n`, "utf8");
}

function ensureLog() {
  const logPath = path.join(wikiDir, "log.md");
  if (fs.existsSync(logPath)) return;
  fs.writeFileSync(
    logPath,
    [
      "---",
      "graph: false",
      "kind: wiki_control",
      "---",
      "",
      "# Log",
      "",
      "Chronological operation record for wiki maintenance.",
      "",
      "## [bootstrap] system | Wiki operation log initialized",
      "",
      "- Created log file.",
      "",
    ].join("\n"),
    "utf8"
  );
}

const pages = readWikiPages(wikiDir).filter((page) => !page.name.replace(/\\/g, "/").startsWith("raw/"));
writeIndex(pages);
writeOverview(pages, readGraph());
ensureLog();
console.log(`Updated ${path.join(wikiDir, "index.md")}, overview.md, and log.md.`);
