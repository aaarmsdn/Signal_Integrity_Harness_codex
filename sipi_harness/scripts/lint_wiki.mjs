import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { asArray, isGraphPage, readWikiPages, wikilinks } from "./wiki_utils.mjs";
import { writeJson } from "./graph_io.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wikiDir = path.join(root, "wiki");
const taxonomyPath = path.join(wikiDir, "taxonomy.yml");
const reportPath = path.join(root, "data", "wiki_lint_report.json");

const REQUIRED_GLOBAL = [
  "graph",
  "id",
  "title",
  "page_type",
  "domain",
  "topics",
  "design_stage",
  "source_tier",
  "source_ids",
  "confidence",
  "status"
];

const ALLOWED_PAGE_TYPES = new Set([
  "source_card",
  "interface_profile",
  "spec_constraint",
  "design_rule",
  "stackup_profile",
  "validation_metric",
  "validation_flow",
  "project_case"
]);

const ALLOWED_SOURCE_TIERS = new Set(["tier_0", "tier_1", "tier_2", "tier_3"]);
const ALLOWED_DOMAIN = new Set(["SI", "PI", "package", "verification"]);

const PAGE_TYPE_REQUIRED = {
  spec_constraint: ["interfaces", "spec_versions", "constraints", "source_ids"],
  validation_metric: ["metric_name", "required_inputs", "extraction_method", "pass_fail_equation", "output_artifacts"],
  design_rule: ["applicability", "design_knobs", "validation_checklist"],
  stackup_profile: ["material", "layer_count", "geometry_parameters", "assumptions"],
  source_card: ["source_type", "source_tier", "version", "access", "allowed_usage"],
  interface_profile: ["interfaces", "supported_package_classes", "design_objects", "required_constraints"],
  validation_flow: ["required_inputs", "steps", "output_artifacts", "pass_fail_gates"],
  project_case: ["problem", "final_strategy", "reusable_rules", "evidence_artifacts"]
};

function issue(issues, severity, file, message) {
  issues.push({ severity, file, message });
}

function hasValue(value) {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return String(value).trim() !== "";
}

function readTaxonomy() {
  if (!fs.existsSync(taxonomyPath)) return {};
  const taxonomy = {};
  const lines = fs.readFileSync(taxonomyPath, "utf8").replace(/\r\n/g, "\n").split("\n");
  const stack = [];
  for (const raw of lines) {
    if (!raw.trim() || raw.trimStart().startsWith("#")) continue;
    const indent = raw.match(/^ */)?.[0].length || 0;
    const line = raw.trim();
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    if (line.endsWith(":")) {
      const key = line.slice(0, -1);
      stack.push({ indent, key });
      continue;
    }
    if (line.startsWith("- ")) {
      const parent = stack[stack.length - 1]?.key;
      if (!parent) continue;
      if (!taxonomy[parent]) taxonomy[parent] = new Set();
      taxonomy[parent].add(line.slice(2).trim().replace(/^"|"$/g, ""));
    }
  }
  return taxonomy;
}

function taxonomySet(taxonomy, ...keys) {
  const out = new Set();
  for (const key of keys) {
    for (const value of taxonomy[key] || []) out.add(value);
  }
  return out;
}

function numericConstraintWithoutSource(constraints) {
  for (const constraint of asArray(constraints)) {
    if (!constraint || typeof constraint !== "object") continue;
    const hasNumeric = ["numeric_limit", "pass_fail_threshold", "limit", "threshold", "value"].some((key) => {
      const value = constraint[key];
      return typeof value === "number" || (typeof value === "string" && /[-+]?\d+(\.\d+)?/.test(value));
    });
    if (hasNumeric && !constraint.source_id) return true;
  }
  return false;
}

const pages = readWikiPages(wikiDir).filter((page) => !page.name.replace(/\\/g, "/").startsWith("raw/"));
const taxonomy = readTaxonomy();
const topicAllowed = taxonomySet(taxonomy, "si_topic", "pi_topic", "routing_topic", "validation_topic");
const interfaceAllowed = taxonomySet(taxonomy, "interfaces");
const stageAllowed = taxonomySet(taxonomy, "design_stage");
const titleSet = new Set(pages.map((page) => page.title.toLowerCase()));
const stemSet = new Set(pages.map((page) => path.basename(page.name).replace(/\.md$/i, "").toLowerCase()));
const issues = [];
const ids = new Map();

for (const page of pages) {
  if (!page.meta || Object.keys(page.meta).length === 0) {
    issue(issues, "warning", page.name, "missing YAML frontmatter");
    continue;
  }

  if (!page.isControl && isGraphPage(page)) {
    for (const field of REQUIRED_GLOBAL) {
      if (!hasValue(page.meta[field])) issue(issues, "error", page.name, `graph page missing required v2 field: ${field}`);
    }
    if (page.meta.id) {
      if (ids.has(page.meta.id)) issue(issues, "error", page.name, `duplicate id also used by ${ids.get(page.meta.id)}`);
      ids.set(page.meta.id, page.name);
    }
    if (!ALLOWED_PAGE_TYPES.has(page.meta.page_type)) {
      issue(issues, "error", page.name, `unknown page_type: ${page.meta.page_type}`);
    }
    if (!ALLOWED_SOURCE_TIERS.has(page.meta.source_tier)) {
      issue(issues, "error", page.name, `unknown source_tier: ${page.meta.source_tier}`);
    }
    for (const domain of asArray(page.meta.domain)) {
      if (!ALLOWED_DOMAIN.has(domain)) issue(issues, "warning", page.name, `unknown domain: ${domain}`);
    }
    for (const topic of asArray(page.meta.topics)) {
      if (topicAllowed.size && !topicAllowed.has(topic)) issue(issues, "warning", page.name, `topic not in taxonomy: ${topic}`);
    }
    for (const iface of asArray(page.meta.interfaces)) {
      if (interfaceAllowed.size && !interfaceAllowed.has(iface)) issue(issues, "warning", page.name, `interface not in taxonomy: ${iface}`);
    }
    for (const stage of asArray(page.meta.design_stage)) {
      if (stageAllowed.size && !stageAllowed.has(stage)) issue(issues, "warning", page.name, `design_stage not in taxonomy: ${stage}`);
    }

    for (const required of PAGE_TYPE_REQUIRED[page.meta.page_type] || []) {
      if (!hasValue(page.meta[required])) issue(issues, "error", page.name, `${page.meta.page_type} missing required field: ${required}`);
    }

    if (page.meta.page_type === "spec_constraint") {
      if (page.meta.source_tier !== "tier_0") {
        issue(issues, "error", page.name, "spec_constraint must use source_tier: tier_0");
      }
      if (numericConstraintWithoutSource(page.meta.constraints)) {
        issue(issues, "error", page.name, "numeric compliance/pass-fail constraint must include source_id");
      }
    }
    if (page.meta.page_type === "spec_constraint" && page.meta.source_tier === "tier_3") {
      issue(issues, "error", page.name, "tier_3 cannot be promoted into final compliance constraints");
    }
    if (page.meta.claim_type === "source_grounded" && page.meta.source_tier === "tier_3") {
      issue(issues, "warning", page.name, "source_grounded design knowledge should not rely on tier_3 only");
    }
    for (const relationship of asArray(page.meta.relationships)) {
      if (typeof relationship === "string") {
        issue(issues, "warning", page.name, "legacy string relationship format is supported but should be converted to structured objects");
      } else if (!relationship?.source || !relationship?.predicate || !relationship?.target) {
        issue(issues, "warning", page.name, "relationship object should include source, predicate, and target");
      }
    }
  }

  for (const link of wikilinks(page.text)) {
    if (!titleSet.has(link.toLowerCase()) && !stemSet.has(link.toLowerCase())) {
      issue(issues, "warning", page.name, `dead wikilink: [[${link}]]`);
    }
  }
}

const graphPages = pages.filter((page) => !page.isControl && isGraphPage(page));
const report = {
  schema_version: "2.0",
  wiki_dir: wikiDir,
  taxonomy: fs.existsSync(taxonomyPath) ? taxonomyPath : null,
  page_count: pages.length,
  graph_page_count: graphPages.length,
  issue_count: issues.length,
  errors: issues.filter((item) => item.severity === "error").length,
  warnings: issues.filter((item) => item.severity === "warning").length,
  infos: issues.filter((item) => item.severity === "info").length,
  issues
};

writeJson(reportPath, report);
console.log(JSON.stringify(report, null, 2));

if (process.argv.includes("--strict") && report.errors > 0) {
  process.exit(1);
}
