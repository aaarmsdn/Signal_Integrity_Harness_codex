import path from "node:path";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (!item.startsWith("--")) continue;
    const key = item.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function detectRequestFields(request) {
  const text = request || "";
  const lower = text.toLowerCase();
  const fields = [];
  const add = (label, value) => {
    if (value) fields.push([label, value]);
  };
  const knownInterfaces = ["UCIe", "PCIe", "CXL", "DDR", "LPDDR", "HBM", "SerDes"];
  const detectedInterface = knownInterfaces.find((item) => new RegExp(`\\b${item}\\b`, "i").test(text));
  add("Interface", detectedInterface || null);
  add("Lane count", text.match(/x\s*(\d+)/i)?.[0]?.replace(/\s+/g, "") || null);
  add("Data rate", text.match(/(\d+(?:\.\d+)?)\s*(?:g(?:bps|t\/s|tps)|gt\/s)/i)?.[0] || null);
  add("Channel length", text.match(/(\d+(?:\.\d+)?)\s*mm/i)?.[0] || null);
  add("Layer count", text.match(/(\d+)\s*[- ]?layer|(\d+)\s*층/i)?.[0] || null);
  add("Package class", lower.includes("standard") ? "standard" : lower.includes("advanced") ? "advanced" : null);
  add("Material Dk", text.match(/d[ki]\s*[:=]\s*(\d+(?:\.\d+)?)/i)?.[0] || null);
  add("Material Df", text.match(/df\s*[:=]\s*(\d+(?:\.\d+)?)/i)?.[0] || null);
  const escapedInterface = detectedInterface?.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const specMatch = escapedInterface
    ? text.match(new RegExp(`\\b${escapedInterface}\\b\\s*(?:spec(?:ification)?\\s*)?(?:rev(?:ision)?\\s*)?(\\d+(?:\\.\\d+)*)\\b`, "i"))
    : null;
  add("Governing spec", specMatch && detectedInterface ? `${detectedInterface} ${specMatch[1]}` : null);
  return fields;
}

function formatDetected(fields) {
  if (!fields.length) return "- No structured fields detected yet.";
  return fields.map(([label, value]) => `- ${label}: ${value}`).join("\n");
}

const args = parseArgs(process.argv.slice(2));
const request = String(args.request || "").trim();
const caseName = String(args["case-name"] || args.case || "<case-name>");
const caseDir = String(args["case-dir"] || path.join("outputs", caseName));
const detected = detectRequestFields(request);

const prompt = `# SI/PI Harness Intake Prompt

## Received Request

${request || "(paste the user's design request here)"}

## Parsed So Far

${formatDetected(detected)}

## Question 1: Missing Design Information

Before I start layout or simulation, please provide any of the following if available. You can also answer "continue with assumptions" and I will mark missing items as assumptions or blockers.

- Governing spec file/path/version and whether it is the controlling tier-0 source.
- Required artifacts: strategy only, KiCad package/PCB, HFSS/AEDB/Touchstone, bench workspace, reports, or all stages.
- Pin, ball, bump, connector, or pad map source. If it is in a PDF figure/table, confirm that I should extract it from the document.
- Stackup details beyond layer count: signal/reference/power layer assignment, copper thickness, dielectric thickness, material Dk/Df versus frequency, solder mask or package buildup assumptions.
- Routing constraints: target impedance, min width/spacing, via/pad size, allowed layers, length/skew budget, reference plane requirements, and keepouts.
- Validation requirements: exact spec clauses/tables/equations, loading model, source/receiver model, BER/mask target, S-parameter/VTF/eye/jitter metrics, and required frequency range.
- Local tool versions and licenses: KiCad, Ansys AEDT/PyAEDT/PyEDB, Keysight ADS, and preferred Python environments.

## Question 2: Source Intake

Do you want to add source material before strategy generation?

- Put governing specs or datasheets in \`sipi_harness/wiki/raw/datasheet/\` or case-local \`${caseDir}/knowledge_intake/user_references/\`.
- Put papers you are allowed to use in \`sipi_harness/wiki/raw/papers/\`.
- Put internal notes or reviewed design comments in \`sipi_harness/wiki/raw/user_notes/\`.
- Put summarized web research in \`sipi_harness/wiki/raw/web_research/\`.
- Supported Docling candidate-ingest formats include PDF, DOCX, PPTX, XLSX, HTML, EPUB, images, Markdown/text, CSV, email, XML, and LaTeX.

If you add sources, I will run source scan, Docling candidate conversion when supported, PDF evidence extraction for governing specs, graph rebuild, and Obsidian export before strategy generation. Copyrighted or restricted sources should stay local and should not be committed to Git.

## Question 3: Design Run Mode Selection

Choose one mode:

1. Stage Review Mode
   - Pause after each stage: Strategy, PCB/Package, EM Solve, Bench, Report.
   - Recommended for new specs, new maps, or first use of a tool path.

2. End-to-End Goal Mode
   - Continue through all stages until final reports exist.
   - If final metrics fail and revision is possible, loop back to Strategy and continue.
   - Review gates are recorded but I do not pause unless an unresolved external blocker is reached.

3. Single-Pass Design Mode
   - Generate one candidate and reports without design-revision loops.
   - Failures are reported as-is with evidence.

This is separate from execution mode: dry_run/execute controls whether EDA tools launch.

Recommended for this request: Stage Review Mode if the governing spec PDF/ball map has not already been extracted and reviewed; otherwise End-to-End Goal Mode for a regression-style run.
`;

console.log(prompt);
