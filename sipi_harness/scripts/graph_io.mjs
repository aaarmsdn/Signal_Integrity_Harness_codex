import fs from "node:fs";
import path from "node:path";

export function emptySourcePayload() {
  return {
    schema_version: "0.1",
    generated_from: "local_runtime_seed",
    documents: [],
    communities: []
  };
}

export function readJsonOrNull(filePath) {
  if (!fs.existsSync(filePath)) return null;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

export function readSourcePayload(sourcePath) {
  return readJsonOrNull(sourcePath) || emptySourcePayload();
}

export function writeJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}
