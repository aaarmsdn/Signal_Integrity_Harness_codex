import fs from "node:fs";
import path from "node:path";

export const CONTROL_FILES = new Set(["index.md", "overview.md", "log.md", "purpose.md", "schema.md"]);

export function slug(value) {
  return String(value || "")
    .toLowerCase()
    .replaceAll("/", "_")
    .replaceAll(" ", "_")
    .replaceAll("-", "_")
    .replace(/[()]/g, "")
    .replace(/[^a-z0-9_]/g, "");
}

function lineIndent(line) {
  return line.match(/^ */)?.[0].length || 0;
}

function stripComment(value) {
  let inSingle = false;
  let inDouble = false;
  for (let i = 0; i < value.length; i += 1) {
    const ch = value[i];
    if (ch === "'" && !inDouble) inSingle = !inSingle;
    if (ch === '"' && !inSingle && value[i - 1] !== "\\") inDouble = !inDouble;
    if (ch === "#" && !inSingle && !inDouble && (i === 0 || /\s/.test(value[i - 1]))) {
      return value.slice(0, i).trimEnd();
    }
  }
  return value;
}

function parseScalar(rawValue) {
  const value = stripComment(String(rawValue || "").trim());
  if (value === "") return "";
  if (value === "null" || value === "~") return null;
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  if (value.startsWith("[") && value.endsWith("]")) {
    const inner = value.slice(1, -1).trim();
    if (!inner) return [];
    return inner.split(",").map((item) => parseScalar(item.trim()));
  }
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1).replace(/\\"/g, '"');
  }
  return value;
}

function splitKeyValue(value) {
  const match = String(value).match(/^([A-Za-z0-9_./-]+):(?:\s*(.*))?$/);
  if (!match) return null;
  return [match[1], match[2] || ""];
}

function parseYamlBlock(lines, startIndex, indent) {
  const first = lines[startIndex];
  if (first && lineIndent(first) === indent && first.trimStart().startsWith("- ")) {
    return parseYamlList(lines, startIndex, indent);
  }
  return parseYamlMap(lines, startIndex, indent);
}

function parseYamlMap(lines, startIndex, indent) {
  const result = {};
  let i = startIndex;
  while (i < lines.length) {
    const raw = lines[i];
    if (!raw.trim() || raw.trimStart().startsWith("#")) {
      i += 1;
      continue;
    }
    const currentIndent = lineIndent(raw);
    if (currentIndent < indent) break;
    if (currentIndent > indent) {
      i += 1;
      continue;
    }
    const trimmed = raw.slice(indent);
    if (trimmed.startsWith("- ")) break;
    const keyValue = splitKeyValue(trimmed);
    if (!keyValue) {
      i += 1;
      continue;
    }
    const [key, value] = keyValue;
    if (value === "") {
      let next = i + 1;
      while (next < lines.length && (!lines[next].trim() || lines[next].trimStart().startsWith("#"))) next += 1;
      if (next < lines.length && lineIndent(lines[next]) > currentIndent) {
        const parsed = parseYamlBlock(lines, next, lineIndent(lines[next]));
        result[key] = parsed.value;
        i = parsed.nextIndex;
      } else {
        result[key] = null;
        i += 1;
      }
    } else {
      result[key] = parseScalar(value);
      i += 1;
    }
  }
  return { value: result, nextIndex: i };
}

function parseYamlList(lines, startIndex, indent) {
  const values = [];
  let i = startIndex;
  while (i < lines.length) {
    const raw = lines[i];
    if (!raw.trim() || raw.trimStart().startsWith("#")) {
      i += 1;
      continue;
    }
    const currentIndent = lineIndent(raw);
    if (currentIndent < indent) break;
    if (currentIndent > indent) {
      i += 1;
      continue;
    }
    const trimmed = raw.slice(indent);
    if (!trimmed.startsWith("- ")) break;
    const itemText = trimmed.slice(2).trim();
    if (itemText === "") {
      let next = i + 1;
      while (next < lines.length && (!lines[next].trim() || lines[next].trimStart().startsWith("#"))) next += 1;
      if (next < lines.length && lineIndent(lines[next]) > currentIndent) {
        const parsed = parseYamlBlock(lines, next, lineIndent(lines[next]));
        values.push(parsed.value);
        i = parsed.nextIndex;
      } else {
        values.push(null);
        i += 1;
      }
      continue;
    }

    const inlineObject = splitKeyValue(itemText);
    if (inlineObject) {
      const [key, value] = inlineObject;
      const item = { [key]: value === "" ? null : parseScalar(value) };
      let next = i + 1;
      if (next < lines.length && lineIndent(lines[next]) > currentIndent) {
        const parsed = parseYamlMap(lines, next, currentIndent + 2);
        Object.assign(item, parsed.value);
        next = parsed.nextIndex;
      }
      values.push(item);
      i = next;
    } else {
      values.push(parseScalar(itemText));
      i += 1;
    }
  }
  return { value: values, nextIndex: i };
}

export function parseWikiFrontmatter(text) {
  const normalized = text.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) return null;
  const end = normalized.indexOf("\n---", 4);
  if (end < 0) return null;
  const raw = normalized.slice(4, end).split("\n");
  return parseYamlMap(raw, 0, 0).value;
}

export function markdownTitle(fileName, text) {
  const match = text.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : path.basename(fileName).replace(/\.md$/i, "");
}

export function wikilinks(text) {
  const withoutCode = String(text).replace(/```[\s\S]*?```/g, "").replace(/`[^`]*`/g, "");
  return [...withoutCode.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g)].map((match) => match[1].trim());
}

export function asArray(value) {
  if (value === null || value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

export function isGraphPage(pageOrMeta) {
  const meta = pageOrMeta?.meta || pageOrMeta || {};
  return meta.graph === true || meta.graph === "true";
}

function walkMarkdownFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walkMarkdownFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      out.push(fullPath);
    }
  }
  return out;
}

export function readWikiPages(wikiDir) {
  if (!fs.existsSync(wikiDir)) return [];
  return walkMarkdownFiles(wikiDir).map((filePath) => {
    const name = path.relative(wikiDir, filePath).replaceAll("\\", "/");
    const text = fs.readFileSync(filePath, "utf8");
    const meta = parseWikiFrontmatter(text) || {};
    return {
      name,
      path: filePath,
      text,
      meta,
      title: markdownTitle(name, text),
      isControl: CONTROL_FILES.has(path.basename(name)) || name.startsWith("templates/")
    };
  });
}
