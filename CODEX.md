# Codex Startup Notes

Start in:

```powershell
cd <repo>
```

Read first:

1. `README.md`
2. `README_AGENT.md`
3. `sipi_harness/package.json`
4. `sipi_harness/spec_evidence_contract.md`
5. `sipi_harness/wiki/purpose.md`
6. `sipi_harness/wiki/schema.md`

This repository is a reusable SI/PI engineering harness. Do not assume the active task is related to any previous case. Treat every new package, PCB, interposer, cable, connector, or I/O task as a fresh spec-driven flow.
Generated strategies, manifests, reports, and tool instructions should be in
English unless quoting a source.

## Initial Intake Gate

When a new design prompt arrives, do not jump directly to run mode selection or
layout. First ask for optional missing information that would materially improve
the case:

- governing spec name/version and source path or URL
- interface/topology, lane count, data rate, channel length, package/PCB class,
  and target artifacts
- stackup, allowed layer count, material Dk/Df, trace/via constraints,
  impedance targets, and reference/power layer intent
- pin/ball/bump/connector map source and whether it comes from a PDF
  figure/table
- compliance metrics, pass/fail limits, loading models, masks, source/receiver
  models, and benchmark tool
- available local EDA tools, versions, licenses, and Python environments

This gate is a hard stop. If the prompt does not explicitly answer the missing
information/source-intake/run-mode questions, ask those questions and wait for
the engineer's reply. Do not infer End-to-End mode, create case folders, install
dependencies, search the web, load stage-specific skills, generate strategy
files, or start layout/simulation from the first design request.

Then ask whether the engineer wants to add source material for the LLM wiki and
case evidence. Point them to:

- `sipi_harness/wiki/raw/datasheet/`
- `sipi_harness/wiki/raw/papers/`
- `sipi_harness/wiki/raw/user_notes/`
- `sipi_harness/wiki/raw/web_research/`
- `outputs/<case>/knowledge_intake/user_references/`

Supported Docling ingestion formats include PDF, DOCX, PPTX, XLSX, HTML, EPUB,
images, Markdown/text, CSV, email, XML, and LaTeX. Use Docling as the preferred
source-intake conversion path when user-provided documents are available; fall
back only when the selected environment cannot run Docling:

```powershell
cd <repo>\sipi_harness
npm run setup:docling
npm run ingest:docling -- --case-dir <case-dir> --source-tier tier_0 <path-to-source>
npm run register:docling
npm run refresh:all
```

Docling output is candidate evidence. Do not promote unreviewed extracted
values into compliance thresholds.

Raw source group hits are metadata only. If a request matches staged files
under `sipi_harness/wiki/raw`, convert the relevant files before strategy
signoff. Prefer the integrated strategy command:

```powershell
npm run register:raw-sources
npm run report:wiki-strategy -- --case-dir <case-dir> --request-file <request.txt> --auto-ingest-sources
```

This command selects request-relevant raw sources, runs case-local Docling
candidate ingest, extracts PDF spec evidence for the best matching PDF, and then
builds `strategy/design_strategy.yaml` from wiki cards plus document/spec
evidence. If a report shows `Raw Source Group: ...` hits but
`docling_hit_count=0`, document contents were not used and the strategy is
incomplete for layout/compliance.
The generated strategy must expose document influence in machine-readable
fields, not only in prose. Check `raw_source_usage`, section-level
`evidence_claims`, `generic_implementation_benches`, and `blocked_benches`
before layout. `generic_implementation_benches` are source-backed checks that
can be run with common geometry/TDR/Touchstone artifacts. `blocked_benches`
are not failures to ignore; they are required adapter-generation gates for
metrics that need a circuit/statistical/tool-specific setup.
Raw source files and Docling extraction outputs are intentionally not committed
to Git. They must be regenerated per case under `outputs/<case>/knowledge_intake/`
or `outputs/<case>/spec_evidence/`.
If a case has `spec_evidence/spec_candidates.json`, the strategy report must
also show `spec_evidence_hit_count > 0`; otherwise the PDF was extracted but
not fused into the strategy.
The typed wiki subfolders under `sipi_harness/wiki/` are scaffold and reviewed
card locations, not pre-approved design knowledge. README-only folders such as
`design_rules/`, `constraints/`, and `stackups/` do not count as strategy
evidence. A strategy can cite a typed card only after that card was generated
or curated from source intake with explicit `source_ids`; raw folder names or
empty wiki folders cannot justify routing, stackup, or bench decisions.

## Background and Subagent Work

Obsidian export is optional and must not block strategy, layout, solve, bench,
or report work. If an engineer wants Obsidian graph browsing, run
`npm run export:obsidian` as a background/subagent task after the wiki graph is
rebuilt. Do not run `npm run refresh:all` in parallel with strategy generation
unless the main agent has explicitly frozen the source registry and wiki graph
inputs for the current case.

Tool-stage subagents are opt-in, not the default. The main agent keeps stage
ownership and should run stateful EDA repair loops itself unless the user
explicitly asks for subagents or the task packet is narrow enough to be
file-in/file-out. Avoid subagents for HFSS setup/sweep repair, Touchstone export
debugging, routing-violation repair loops, or ADS connectivity debug because
those tasks require continuous context across tool logs, generated files, and
stage gates. Use subagents only for bounded, file-based tasks such as:

- KiCad/package generation and geometry reports.
- HFSS/PyAEDT import, port validation, solve, and Touchstone export.
- ADS/bench workspace generation, netlist/dataset checks, and plots.
- Optional Obsidian vault export.

The main agent must still define the stage goal, hand off exact input paths,
review returned artifacts, update the manifest, decide pass/proxy/blocked
status, and pause at Stage Review gates. Subagents must not invent missing spec
limits, change run mode, skip source evidence, substitute proxy data, or claim
compliance without main-agent review of evidence and generated artifacts.

## Run Mode Gate

At the start of a new design case, ask the engineer to choose one run mode and
record the answer in the case manifest before layout or simulation:

These run-mode and stage-gate rules are repository defaults. A user demo prompt
should not need to repeat the detailed pause/report/evidence instructions; if a
prompt only provides a design request and a run mode, apply the rules in this
file.

There is no default run mode. If the engineer has not selected Stage Review,
End-to-End Goal, or Single-Pass Design mode, stop and ask. Never treat an
unspecified mode as permission to run end-to-end.

1. Stage Review Mode: finish one stage goal, produce its required artifacts and
   report, then pause for engineer review before continuing. Pause after all
   five stages: Strategy, PCB/Package, EM Solve, Bench, and Report.
2. End-to-End Goal Mode: continue through strategy, layout, EM solve, benchmark,
   and final report until complete. If the final report shows failed metrics
   and revision is possible, loop back to Strategy and continue automatically.
   Stop only on unresolved external blockers such as missing user evidence,
   missing license/tool access, or impossible constraints.
3. Single-Pass Design Mode: produce one design candidate and reports without a
   design-revision loop; report failures as-is.

Design run mode is separate from tool execution mode. Use
`harness.design_run_mode` for Stage Review, End-to-End Goal, or Single-Pass
Design, and `harness.execution_mode` for `dry_run` versus `execute`.

For every mode, define stage goals explicitly:

- Strategy: `design_strategy.yaml`, strategy PDF, source lineage, and missing
  spec values.
- PCB/Package: KiCad/project/layout bundle, route records, geometry report, and
  port-intent JSON.
- EM Solve: imported AEDB/AEDT or equivalent solver project, verified ports,
  solve status, and valid Touchstone or a blocker.
- Bench: benchmark workspace/netlist/schematic, datasets, metric plots, and
  pass/fail/proxy status.
- Report: stage PDFs, final report, manifest, and shareability notes.

Repeat/fix within a stage until the required output exists or a blocker is
explicitly recorded. Do not advance from a stage based only on partial file
generation.

Do not start PCB/package layout generation until the Strategy stage has written
all planning artifacts: `strategy/design_strategy.yaml`, the strategy PDF,
evidence gaps or blockers, and the case manifest entry. Compliance thresholds
must come from reviewed tier-0 evidence; otherwise the strategy may proceed only
as proxy or blocked.

If a governing PDF, datasheet, or raw-source group is available, raw-source
metadata alone is not a strategy input. Before PCB/package generation, the
strategy gate must show content-level evidence: Docling/spec-extraction hit
counts, cited page/table/figure/equation records, and a metric coverage matrix.
If `docling_hit_count == 0`, `spec_evidence_hit_count == 0`, or the coverage
matrix has no implemented/blocked row for a discovered spec requirement family,
do not route. Continue evidence extraction/fusion first or mark Strategy
blocked.

Stage reports are run-mode independent. Whenever a stage boundary is crossed,
run `npm run report:checkpoint -- --case-dir <case-dir> --stage <stage>
--status completed|proxy|blocked|failed` before moving to the next stage. This
applies to Stage Review Mode, End-to-End Goal Mode, and Single-Pass Design Mode.
The checkpoint must update `reports/stage_report_manifest.json` and
`manifest.json.stage_report_checkpoints`.

Failure lessons are also run-mode independent. When a stage fails, is
misdiagnosed, or is repaired after a wrong attempt, record the root cause and
the corrected rule in `sipi_harness/docs/agent_lessons.md` or the relevant
skill/workflow document before final commit. Do not leave the learning only in
scripts, logs, generated reports, or chat history. The note must be general
enough to prevent the same class of error on another interface, package,
solver, or bench.

In Stage Review Mode, stop for explicit setup review before running expensive
or compliance-sensitive execution:

- After KiCad/package generation and before HFSS handoff, render a layout
  preview with `npm run render:kicad-preview -- --board <board.kicad_pcb>
  --output <case-dir>\reports\kicad_layout_preview.png --manifest
  <case-dir>\manifest.json`, show the image to the engineer when possible, and
  run `npm run prompt:stage-review -- --stage pcb ...`.
- Before HFSS solve, run `npm run prompt:stage-review -- --stage hfss ...` and
  show the proposed AEDT version, import path, port method, port count, sweep
  type, frequency range, point count, and Touchstone target.
- Before ADS/bench verification, run
  `npm run prompt:stage-review -- --stage ads ...` and show the Touchstone
  mapping, bench type, source/load/spec-equation status, workspace target, and
  report outputs.
- Continue working within each stage until the setup is reviewable; then wait
  for approval before running solve or bench verification.

## General Flow

For any new task, follow this order:

1. Ask for missing design information that would materially improve the case.
2. Ask whether source/wiki data will be added, and run scan/intake plus Docling/PDF extraction after the user provides or confirms sources.
3. Select the run mode and stage goals.
4. Identify the governing specification, data rate, topology, stackup/package constraints, allowed layer count, and target artifacts.
5. Initialize knowledge intake for the case. Search the internet for credible design-strategy sources relevant to the request, store the summarized/cited results under `outputs/<case>/knowledge_intake/web_research/`, and register user-provided or user-approved documents under `outputs/<case>/knowledge_intake/user_references/`.
6. Fuse web research plus user references into the case LLM wiki strategy input. The wiki is built from existing reusable pages plus the two intake streams; do not rely on memory-only strategy.
7. Read the governing spec directly before layout: extract relevant text, tables, figures, pin/ball maps, equations, loading models, and page/figure references into a case-local `spec_evidence/` artifact. If a pin map, ball map, connector pinout, escape diagram, mask, or loading network is shown as a PDF figure, inspect the figure itself using text extraction plus visual/vector/image evidence before creating coordinates. Do not substitute a remembered or "spec-like" map for a figure/table in the PDF.
8. Build a spec compliance metric coverage matrix before strategy signoff. The matrix must scan the whole governing source for every requirement family, not only the user's prompt terms: frequency-domain S-parameters or transfer functions, impedance/TDR, crosstalk, skew/timing, jitter, transient waveform/eye/mask, BER/bathtub/contour, loading/source/receiver models, PDN/rail limits where applicable, and report artifacts. Each discovered family must map to a validation bench or an explicit `blocked_missing_evidence`/`not_applicable` row. If an eye mask, eye diagram, BER contour, bathtub, or jitter requirement exists in the spec, an S-parameter-only bench is not sufficient for compliance.
9. Confirm that extracted figure/table evidence is actually used as design input. For maps and pinouts, the generated coordinates, nets, ports, and routing constraints must reference the extracted row/column/pin records; do not merely store the evidence as an annotation while generating a proxy layout from a simplified pattern.
10. If the governing spec provides a bump/ball/pin map, use that map as the primary routing endpoint source. If the spec does not provide one, generate a case-local synthetic bump/ball/pad map from the requested lane count, pitch, topology, package class, and connector/die placement assumptions before routing. Store it under `outputs/<case>/routing/` or `outputs/<case>/spec_evidence/` with `source_type: synthetic`, assumptions, pitch, row/column coordinates, and proxy/compliance status. Do not route directly from an implicit mental map.
11. Build a design strategy before layout or simulation. The strategy must list the required testbenches, simulator inputs, pass/fail equations, loading models, reports, and final artifacts. If the spec contains eye/mask/BER, transfer-function, crosstalk, impedance, skew, jitter, PDN, or loading requirements, those requirements must appear in the strategy before routing starts.
12. Before PCB/package geometry generation, create a wiki-derived `strategy/design_strategy.yaml` and design-strategy PDF under the active case `strategy/` folder. This report is a planning gate and must cite the web research, user references, wiki/design knowledge used, expected geometry checks, solver handoff, and final spec benches. The wiki supplies design strategy; this file and skills define toolchain execution.
13. Generate complete design artifacts, not partial files. For PCB work this means project, board, schematic where applicable, stackup, nets, port-intent metadata, manifest, and reports.
14. Export to the solver through a documented path, usually KiCad/project data -> ODB++/AEDB -> HFSS 3D Layout or another solver.
15. Solve until the expected Touchstone or field-solver output exists, then verify the file dimensions, port count, port order, frequency range, and metadata.
16. Build ADS or equivalent verification benches from the spec strategy, not from memory.
17. Run simulation, extract metrics, compare against the exact spec equations, and write a pass/fail report.
18. Update the case manifest and reports. Keep this startup file general.

## Hard Rules

- Do not claim compliance from a proxy unless the report clearly says it is only a proxy.
- If the governing spec/evidence contains VTF, XT equations, explicit loading,
  eye diagram, eye mask, BER contour, bathtub, jitter, or another
  spec-defined benchmark, do not run the spec-neutral S-parameter fallback as
  the Bench stage result. Implement the exact benchmark or mark Bench blocked
  with `blocked_missing_spec_bench_implementation`. A fallback S-parameter
  report is allowed only as an explicit diagnostic supplement.
- For every new design request, create or update case knowledge intake before layout. If internet research, Docling conversion, PDF evidence extraction, or user-reference ingestion is skipped, record why in the manifest and mark the strategy as incomplete/proxy where applicable.
- Internet research must be summarized with URLs, source type, access date, claims, design implications, and verification implications. Do not paste long copyrighted source text into the repository.
- User-provided references belong in `outputs/<case>/knowledge_intake/user_references/` or another user-approved local folder. Keep copyrighted specs/books out of Git unless rights are explicit.
- The pre-PCB LLM wiki strategy must combine existing wiki pages, web research, and user references. It must not be produced from existing wiki pages alone when the request is for a new application/spec.
- For any spec-provided pin map, ball map, connector pinout, mask, or table, store the extracted evidence and page/figure/table identifiers under the case folder before routing.
- A figure-derived map is not accepted as design input until the case evidence records: source PDF path, page number, section/table/figure ID, extraction method, raw extracted rows or coordinates, visual snapshot or crop path when available, assumptions/normalization steps, and reviewer status. If any of these are missing, mark the map as unreviewed/proxy and do not claim compliance from it.
- If no spec-provided bump/ball/pin map exists, generate a synthetic map explicitly before routing. The synthetic map must record its assumptions, pitch, row/column order, lane mapping, side/module placement, and why no tier-0 map was available. It can support topology exploration and EM proxy extraction, but compliance claims must say that endpoint placement is synthetic unless the governing spec allows arbitrary placement.
- A generated design must include an evidence-to-geometry audit: each spec-derived signal/pin/ball used for a net or port must record the source row/column/pin identifier and the generated coordinate. If the layout uses simplified, synthetic, or reordered coordinates, mark the design as a proxy and do not claim spec compliance.
- If a spec/table/figure bump, ball, or pin map is available, do not flatten it
  into straight parallel launch rows just because routing is difficult. Route
  from the extracted map itself, or create a reviewed fanout/escape stage that
  preserves the source-map audit. A case endpoint map that records source
  bumps/balls/pins but marks the routed coordinates as proxy/fanout escape is a
  PCB/package blocker by default; do not send it to HFSS as a valid candidate.
- The active case must have a pre-PCB wiki strategy report before layout generation. If it is missing, create it with `sipi_harness/scripts/generate_wiki_strategy_report.py` and record it in the manifest before continuing.
- For PDF spec evidence, run `npm run setup:pdf-python` or `scripts/bootstrap_pdf_python_deps.py` in the selected Python environment before relying on figure render evidence. PyMuPDF is the preferred renderer for full page PNGs.
- Do not let old example generators drive a new task by default. Example
  generators are templates only; they are not generic PCB/package generators.
  For every new spec or application, read the governing PDF/table/figure
  evidence first, then create or adapt a case-specific generator/strategy that
  records the source evidence and assumptions.
- Before solver handoff, run a geometry sanity gate on the generated package/PCB/interconnect: pad/via/pin overlap clearance, trace-to-trace corridor clearance, same-layer crossing/short checks, routed centerline length per channel, estimated delay skew versus the active UI, unconnected nets, and port pad/reference availability. Do not rely on nominal endpoint spacing, preview images, KiCad DRC alone, or generated-file existence as proof of a valid layout.
- For every generated KiCad board, run `npm run check:kicad-geometry -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_same_layer_geometry.json --manifest <case-dir>\manifest.json` before HFSS handoff. This checker is mandatory even when the preview image looks clean or KiCad DRC reports no violations. If it reports same-layer crossings, same-layer shorts, trace-to-pad/via shorts, or pad/via overlaps between different nets, stop and reroute or record the board as blocked/proxy; do not send it to HFSS as a valid candidate.
- KiCad geometry checks are not enough after direct KiCad-to-AEDB conversion. The converter can create extra trace-outline, launch-pad, junction-pad, via-pad, or port-tab polygons that do not exist as simple KiCad segments. After every ODB/IPC/direct-AEDB import, run the AEDB primitive overlap gate and block HFSS if any same-layer different-net polygon primitives overlap. A board that passes KiCad DRC but fails AEDB primitive overlap is not a valid EM candidate.
- Before routing, define the stackup and derive allowed routing layers from it. Do not treat total layer count as routing layer count. A normal 4-layer PCB generally means L1/L4 are signal layers while L2/L3 are reserved for GND/PWR or GND/GND reference planes; routing on internal plane layers is only allowed when the strategy explicitly defines those layers as signal layers, such as in a package/interposer stackup.
- Every routed high-speed channel must record its reference layer/plane assumption. If a route lacks a continuous adjacent return path, mark the layout as a topology proxy and do not use it as an HFSS/ADS compliance candidate.
- Reference continuity is a hard electrical contract, not a cosmetic layout
  option. Local GND launch tabs or port-reference patches are not substitutes
  for a continuous route return path. If a repair attempt removes, fragments,
  or stops generating the assigned reference plane/layer, the PCB/package stage
  is failed and must be rerun before HFSS. Do not proceed to HFSS with a design
  that only has signal traces and port tabs.
- For KiCad/package routes derived from ball maps, pad maps, connector pinouts, or pin tables, use A* or an equivalent deterministic router to generate route waypoints. Allow 45-degree diagonal routing by default (`allow_diagonal: true`) unless manufacturing rules, the governing spec, or the design strategy explicitly prohibit it. Prefer 45-degree bends and avoid unnecessary 90-degree turns in high-speed channels; use 90-degree corners only when an explicit escape/clearance constraint requires them. Diagonal routes must still pass same-layer crossing/short checks and clearance inflation. Store the route request/result and never draw arbitrary LLM-chosen crossing paths.
- Do not disable diagonal routing as a quick fix for a failed geometry gate. If a diagonal route creates crossings, repair by changing lane order, fanout, layer assignment, keepouts, spacing, endpoint pairing, or stackup constraints while keeping `allow_diagonal: true`. Set `allow_diagonal: false` only when the strategy records a manufacturing/spec reason and the engineer approves the exception. A missing route record, `allow_diagonal: false` without approval, or avoidable orthogonal-only/90-degree route is a PCB gate failure.
- Route for minimum centerline length first. Endpoint/lane ordering and allowed-layer selection should minimize total route length and obvious crossings before skew-matching detours are added. If the strategy/spec contains a target impedance, estimate initial KiCad trace width/spacing from the active stackup/material before routing and record the target, formula/model, Dk/Df, reference layer, applied width/spacing, estimated Z0, and any pitch/clearance clamp. Treat this as pre-layout guidance only; HFSS/bench results remain required for compliance.
- In End-to-End Goal Mode, routing violations trigger a repair loop, not a final stop. If `check:kicad-geometry` reports same-layer crossings, shorts, pad/via overlaps, or trace-to-pad/via shorts, rerun deterministic/A* routing with revised lane order, diagonal routing enabled, adjusted keepouts, alternate allowed signal layer, fanout/escape revision, or strategy-approved spacing/stackup changes until the geometry gate passes or a concrete blocker is recorded with attempted alternatives.
- In Single-Pass Design Mode, "single pass" means one design candidate and no post-report design revision loop. It does not permit invalid stage artifacts. Same-layer shorts, failed port gates, missing Touchstone, broken ADS connectivity, or missing required reports must still be repaired within the current stage or reported as a blocker.
- For length-sensitive multi-lane channels, store actual routed centerline length and delay estimate for every lane in the case manifest. The design is not ready for EM solve if the required skew budget is missing, computed from nominal length only, or failing.
- Before claiming compliance, verify the exact spec equations and loading model. Do not substitute a convenient ratio, S-parameter, or single aggressor when the spec defines a different measurement.
- Before claiming compliance, verify coverage rather than one convenient metric. The strategy and report must show a `spec_metric_coverage` or equivalent table listing each requirement family discovered in the governing source and its status. Missing eye/mask/BER/jitter/transient requirements are blockers when the source contains them, even if frequency-domain S-parameter checks pass.
- Every simulator handoff needs explicit port intent: signal net, reference net/layer, port type, positive launch coordinate or pad/ball, local reference geometry selector, and expected port order.
- For KiCad-to-AEDB fallback, use AEDB polygon-edge circuit ports by default.
  The required import method is `--port-method edb_polygon_edge`.
  `edb_path_edge`, coordinate `circuit` ports, and `pin` ports are debug
  overrides only. Do not use them as automatic retries, because they can create
  visible port labels on long trace side edges, wrong Start/End edges, or
  misplaced coordinates while still failing Touchstone export. Run
  `npm run check:port-launch -- --board <board.kicad_pcb> --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --summary <case-dir>\reports\port_launch_clearance.json`
  before HFSS import/solve; it must prove the launch and reference geometry are
  available and that reference placement avoids via holes/antipads.
- HFSS 3D Layout circuit-port placement is a high-risk failure point. Treat it as a hard gate, not a warning. A port label in the GUI, a non-empty `app.port_list`, or `analyze_setup() == true` does not prove the port is exportable. The only acceptable EM handoff is a non-empty Touchstone with expected port count/order/frequency range.
- For polygon-edge circuit ports, the reference edge/primitive must be local to the signal launch edge. Do not choose an arbitrary distant GND primitive just because it is on copper. Long effective port spans can solve and still fail `ExportNetworkData` with "solution data is not available". Keep the launch/reference pair local and run `check:port-launch`.
- If the closest facing reference edge/point is inside a via drill, antipad, or via-clearance keepout, use the nearest adjacent solid reference edge/primitive. Do not reroute the channel or move the signal launch first. Record the selected reference primitive/edge, via distance, and clearance evidence in `port_launch_clearance.json`. Do not add `negative_x`/`negative_y` to an `edb_polygon_edge` intent; those fields are allowed only in a documented coordinate-port debug override with `--allow-coordinate-port-override`.
- The signal side of a polygon-edge port must be a short terminal launch
  edge/pad/tab near the requested coordinate, not the long side of a routed
  trace. If the selector cannot find a short terminal-like edge, fix the
  source layout by adding a non-overlapping endpoint launch pad/tab or by using
  the proper bump-to-bump route generator. Do not retry with `edb_path_edge`.
- Required polygon-edge import pattern for HFSS 3D Layout is:

```powershell
npm run import:hfss3dlayout -- --port-method edb_polygon_edge --edge-port-type Gap --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json ...
```

- Coordinate circuit-port creation is a manual/debug override, not the default:

```python
oeditor.CreateCircuitPort([
    "NAME:Location",
    "PosLayer:=", "F.Cu",
    "X0:=", "2.000mm",
    "Y0:=", "2.540mm",
    "NegLayer:=", "In1.Cu",
    "X1:=", "1.895mm",  # nearby solid GND, outside via/antipad keepout
    "Y1:=", "2.540mm",
])
```

- If the design imports as polygon/path primitives, use a primitive-edge circuit port with an explicit reference primitive/edge. This is the preferred KiCad/AEDB handoff pattern and it still must produce a verified Touchstone:

```python
port = h3d.create_edge_port(
    assignment="SIGNAL_PORT_TAB",
    edge_number=selected_signal_edge,
    is_circuit_port=True,
    reference_primitive="GND_PORT_TAB",
    reference_edge_number=selected_reference_edge,
)
if not port:
    raise RuntimeError("HFSS 3D Layout circuit edge-port creation failed")
```

- Polygon-edge port selection must attach to a terminal-like launch edge, not a long trace side edge. Reject candidate edges that are too long, too far from the port intent coordinate, or located on the side of a routed trace rather than the short end/launch pad. If the selector cannot find a short local signal edge and local reference edge, fail import and fix the layout/port tab instead of accepting a visually misplaced port.
- If solve succeeds but Touchstone export reports missing solution data, first inspect whether the project used coordinate/pin ports instead of the required polygon-edge import path. Rebuild with `--port-method edb_polygon_edge`, verify setup/sweep registration, and rerun solve/export. Repair two-point coordinates only for an explicit coordinate-port debug override.
- For HFSS 3D Layout AEDB solves, never force `design="PCB"` or another generic name unless that exact imported design already exists. Let `Hfss3dLayout` open the imported AEDB cell, or use the imported design name recorded in the import summary. Before solve, require `app.port_list` to contain the expected ports; if it is empty, stop and fix the handoff instead of solving.
- Validate generated schematics twice: visually in the tool GUI when practical, and by exported netlist or equivalent machine-readable connectivity.
- For benchmark benches, confirm the Touchstone or waveform inputs are in the expected workspace/location, tool-specific filename syntax is valid, and dataset/plot paths resolve.
- For new ADS machines, broken workspaces, or uncertain ADS symbol/API behavior, first run `npm run bench:ads-workspace -- --workspace <case-dir>\bench\ads_bench_wrk --port-count <2*lane_count> --overwrite`. Use the generated SnP, loaded AC, 3-lane smoke ChannelSim, and full N-lane ChannelSim bench workspace plus `reports/*.netlist.log` as a baseline. The full N-lane ChannelSim netlist must show lane-pair SnP order such as `S16P:... tx0 rx0 ... tx7 rx7 0` and a quoted plain Touchstone filename such as `File="channel.s16p"`. Do not use a smoke/example bench as compliance evidence without replacing the source/load/model/equation details from reviewed strategy/spec evidence.
- ADS smoke workspaces are not compliance results. A 3-lane or `.s6p` smoke bench must not be used for an 8-lane, 16-lane, or other N-lane compliance bench. Generated case/demo workspace, cell, and netlist names must not include `template`; use names such as `ads_bench_wrk` and `channelsim_full_8lane_eye`. For lane-count N, build the bench from the full S(2N)P Touchstone, run every required victim lane, include all N-1 aggressor lanes when the spec defines crosstalk/eye with aggressors, and record the victim/aggressor coverage table.
- ADS has two valid automation paths: inspectable workspace/schematic creation
  and deterministic netlist/simulator execution. For spec-defined compliance
  benches, the default completion state is `schematic_plus_netlist`: an ADS
  workspace and schematic exist, the Touchstone is in the workspace `data/`
  folder with ADS-valid filename syntax, and an exported netlist/dataset proves
  connectivity. A netlist-only `.ckt` run is a diagnostic or intermediate repair
  step, not a valid Bench-stage closure, unless the engineer explicitly requests
  netlist-only output.
- Do not silently abandon schematic generation because ADS DE placement, OA
  locks, or symbol APIs are difficult. If schematic generation fails, record
  `bench_mode: blocked_missing_schematic` with logs and keep repairing the ADS
  workspace/schematic/netlist path. Legacy microstrip ADS scripts are examples
  only and must not become the generic multi-lane/spec bench path.
- If no spec-specific benchmark is available, do not skip the bench/report stage. Create a spec-neutral S-parameter fallback bench from the Touchstone with `npm run bench:sparameter`, plot insertion loss, return loss, and crosstalk where applicable, and label the result as sanity/proxy evidence rather than compliance.
- For KiCad to HFSS 3D Layout handoff, generate explicit port intent while creating the KiCad board. Each port intent needs signal net, reference net/layer, positive launch coordinate or pad/ball, local reference geometry selector, port type, impedance, and expected order. The HFSS import step must read this JSON and create AEDB polygon-edge circuit ports by default, then reopen the saved AEDT project and verify port count/order before solve.
- For HFSS/PyAEDT solve automation, do not trust `analyze_setup()` alone. Before running a long solve, verify the setup and sweep are registered in the native AEDT solution tree with `oDesign.GetModule("SolveSetups").GetSetups()`, `GetSweeps(setup)`, and `GetAllSolutionNames()`. A PyAEDT setup object or visible GUI port is not enough; if `Setup1` or `Sweep1` is missing natively, repair setup/sweep creation before solve/export. A visible Sweep1 is also not enough: HFSS 3D Layout can contain a sweep object with an empty frequency table or an unsolved sweep and then expose only `Setup1 : Last Adaptive`. Create or repair sweeps with `Hfss3dLayout.create_linear_count_sweep(...)`, or native `Sweep3DLayout` template args where `Sweeps.Data` is `LINC <start>GHz <stop>GHz <points>`. Do not use only generic `RangeStart`/`RangeEnd` properties for HFSS 3D Layout sweeps. Analyze the requested `Setup : Sweep` as a blocking operation and probe report-visible solution data for that exact sweep before export; do not hand off `Last Adaptive` single-frequency data to ADS. Inspect AEDT logs and result profiles for `Out of memory`, stale `.asol_priv` locks, `Status=Error`, invalid solution messages, convergence status, completed sweep range, and a non-empty Touchstone file before handing off to ADS. Pass the intended AEDT version explicitly to every import, solve, and export command, and reject a solve/export summary produced by a different AEDT major release. Non-graphical AEDT sessions started by the harness must be closed after success or failure so stale `ansysedt.exe -grpcsrv -ng` processes do not accumulate.
- If a polygon-edge HFSS 3D Layout import has correct ports but Touchstone export reports no solution data, check setup registration before changing geometry. A correct ported `.aedt` can still have no exportable solution if the solve setup/sweep was never added to the native AEDT design. Use native `SolveSetups.Add(...)` / `AddSweep(...)` or the harness solve script's setup gate, save, reopen, then confirm `GetAllSolutionNames()` includes `Setup1 : Sweep1`.
- For HFSS 3D Layout export failures, run both PyAEDT export and native AEDT `ExportNetworkData` confirmation when practical. If both report no solution data or `GetAllPortsList`/boundary-module errors while ports appear in the GUI, classify the EM stage as `invalid_or_non_exportable_hfss3dlayout_ports`, rebuild the port method, or block EM. Do not proceed to compliance.
- If EM export is blocked, do not synthesize or substitute proxy S-parameters. Keep repairing the real handoff until a verified non-empty Touchstone exists, or stop with an explicit blocker and stage report. Repair actions include rerouting failed geometry, changing port method, rebuilding AEDB from source layout, reopening in the required AEDT version, running native export, and simplifying the candidate layout while preserving the requested design intent.
- HFSS failure must not trigger an electrically weaker reroute. If a reroute is
  needed after HFSS import/solve/export failure, it must preserve the active
  strategy's stackup, reference-plane coverage, port-reference model, impedance
  intent, and diagonal-routing rule. Any reroute that removes the reference
  plane or changes all layers into signal-only routing invalidates the EM
  candidate and must be rejected before import.
- If ADS/spec bench execution is blocked, do not substitute proxy datasets as the Bench stage result. Keep repairing the real ADS workspace/netlist/dataset/report until the required benchmark artifacts exist, or stop with an explicit blocker and stage report. Diagnostic plots may be produced only as supplemental evidence and must not close the stage.
- ADS syntax errors are hard blockers. Every generated ChannelSim/SnP/AC netlist
  must run through the matching ADS `hpeesofsim` from a clean run directory, with
  captured logs scanned for syntax, parse, and unexpected-token errors. If any
  such error appears, repair the generated netlist/workspace before considering
  the Bench stage complete.
- For ChannelSim eye/BER benches, the runnable `.ckt` must be the ADS-DE
  exported schematic netlist promoted from `reports/*.netlist.log` whenever
  that netlist exists. Do not run a reduced hand-written ChannelSim `.ckt` for
  closure; it can omit Eye Probe defaults such as `Save_Contour`,
  `Save_WidthAtBER`, `Save_HeightAtBER`, `BERContour=list(<target BER>)`, and
  ultra-low-BER settings. If the simulator log does not confirm ultra-low BER
  for a target below the normal floor, repair the ADS bench instead of reporting
  a missing/open BER contour.
- Fresh-clone reproducibility is a gate. Do not use ignored local experiment
  scripts for ADS compliance. If the strategy contains source-backed metric
  families that generic checks cannot close and a verified Touchstone exists,
  do not stop after `plan:bench-adapter`. Run the case-local ADS bench synthesis
  and execution path:
  `npm run bench:ads-from-strategy -- --strategy <case-dir>\strategy\design_strategy.yaml --touchstone <channel.sNp> --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --data-rate-gbps <rate> --workspace <case-dir>\bench\ads_from_strategy_wrk`.
  This command creates the adapter contract, creates ADS bench workspace and
  full-lane netlists, runs source-derived VTF/XT when present, and attempts the
  full-lane ChannelSim eye/BERContour bench when required. A missing static
  interface adapter is not a valid final blocker once the strategy has enough
  source-derived inputs and a verified Touchstone. If ADS still fails, the
  blocker must cite the ADS workspace/netlist/dataset/log or missing spec data,
  not "adapter missing." Use `bench:ads-workspace` only to validate ADS
  symbol/netlist patterns on the target machine. Do not silently run a
  microstrip, 3-lane, or S-parameter fallback bench as compliance.
- The ADS report step is not complete until visual evidence is generated and
  included in the case reports. Frequency-domain benches must include
  result-vs-spec plots such as VTF loss and XT versus frequency with spec
  overlays. Eye/mask benches must include ADS eye density, BERContour at the
  target BER, and the rectangular/spec mask overlay for every victim lane in
  the active lane count. A lane-0-only eye is a smoke result, not N-lane
  closure. If ADS cannot reliably store multiple eye probes in one ChannelSim
  run, run one victim-lane ChannelSim case per lane and combine the results into
  the all-lane report. This is the default robust path because ADS can crash or
  leave dirty partial datasets when several Eye Probe/ModelExtractor components
  are evaluated in one ChannelSim run, and shortened hand-written Eye Probe
  lines can produce trivial density data. Use the full ADS-DE ModelExtractor
  settings for per-lane runs. Run
  `report:stages --bench-workspace <ads workspace>` after the case-local ADS
  adapter writes its workspace, datasets, plots, and summary so
  `03_bench_report.pdf` carries the same visual evidence as the ADS bench.
- For ADS ChannelSim eye benches, prefer the schematic-run dataset under
  `<ads workspace>\data\channelsim_full_<N>lane_eye.ds` when extracting
  density and BERContour for reports. Treat `netlist_runs\*.ds` as a smoke or
  diagnostic dataset unless it is the only explicitly requested deliverable.
  Do not overwrite an existing schematic-run `data\*.ds` while regenerating
  ADS bench workspaces; preserve it and extract `ChannelSim1.TDM.Eye.*` variables
  from that dataset.
- Before running ADS ChannelSim eye/BER benches, audit the verified EM
  Touchstone frequency grid. If it is undersampled for eye analysis, create a
  case-local `_eye_interp.sNp` file using complex linear interpolation in RI
  domain, preserve port order, and run the eye bench from that dense file.
  Record the original and interpolated filenames, point counts, max frequency
  step, and interpolation method in `eye_touchstone_preprocess_summary.json`.
  This is deterministic preparation of a verified EM Touchstone, not proxy
  S-parameter generation.
- Before ADS, verify Touchstone electrical order. If HFSS exports ports in a
  physical order that does not match the spec bench, reorder with
  `npm run touchstone:reorder-ports` and store the summary. A full-lane bench
  must use all S(2N)P ports and run every required victim lane.
- For transient-domain mask checks, report height and width separately, convert time to UI using the active data rate, and only mark the mask pass when all required dimensions pass.
- Keep case-specific state in `outputs/<case>/manifest.json` and generated reports. Do not put active-case assumptions into `CODEX.md`, `README.md`, or `README_AGENT.md`.
- Context compaction is expected on long EDA runs. Before and after every stage, and before any command expected to run longer than several minutes, write or update `outputs/<case>/agent_state.md` or `outputs/<case>/agent_state.json` with: active case path, run mode, current stage goal, required artifacts, exact next command, tool versions/Python paths, no-proxy rules, blockers, and handoff files. After any context transition, read `CODEX.md`, `README_AGENT.md`, `sipi_harness/docs/workflow.md`, the case `manifest.json`, latest `reports/stage_report_manifest.json`, and `agent_state` before acting.
- Do not use the `llm-optimizer` skill for the default harness flow. Strategy comes from the typed LLM wiki, spec evidence, and case strategy artifacts. Optimization loops may be added only when the user explicitly asks for an optimization study after the baseline workflow is valid.
- Do not edit files under `sipi_harness/examples/` during a case run. Examples are reference material. If a case needs a modified generator, create a case-local copy under `outputs/<case>/automation/` or add a new reusable script intentionally with a separate committed change.
- Preserve existing user/generated files. Do not delete AEDT/ADS/KiCad outputs unless the user explicitly asks for overwrite.

## Tool Notes

- Use `sipi_harness/package.json` as the command index.
- Keep wiki operating files current: `npm run wiki:ops` updates `wiki/index.md`, `wiki/overview.md`, and initializes `wiki/log.md`; `npm run lint:wiki` writes the lint report and surfaces graph gaps.
- Assume `AEDT_PYTHON` and `PYAEDT_PYTHON` are unset on a fresh machine. `sipi_harness/scripts/run_aedt_python.mjs` must first search installed Ansys Electronics Desktop CPython runtimes under `C:\Program Files\ANSYS Inc\v*`, probe candidates for `ansys.aedt.core` and `pyedb`, and only then fall back to optional override/user environments such as conda. Do not assume a machine has a personal `aedt_env`.
- On typical Windows installs, valid AEDT CPython candidates include paths such as `C:\Program Files\ANSYS Inc\v251\AnsysEM\commonfiles\CPython\3_10\winx64\Release\python\python.exe`, `C:\Program Files\ANSYS Inc\v251\AnsysEM\common\commonfiles\CPython\3_10\winx64\python\python.exe`, or `C:\Program Files\ANSYS Inc\v251\commonfiles\CPython\3_10\winx64\Release\python\python.exe`.
- If no candidate imports `ansys.aedt.core` and `pyedb`, do not proceed with HFSS automation. Point the engineer to `https://aedt.docs.pyansys.com/version/stable/Getting_started/Installation.html` and suggest either `python -m pip install -U pyaedt pyedb` for their selected Python or `npm run setup:aedt-python` from `sipi_harness` after they approve the target Python.
- Set `HPEESOF_DIR` and/or `ADS_PYTHON` when running ADS automation. ADS 2025 Update 2 or newer is expected; the default known-good path is `C:\Program Files\Keysight\ADS2026_Update2\tools\python\python.exe`.
- ADS automation requires ADS 2025 Update 2 or newer unless an explicit compatibility patch is made.
- ADS DE API calls usually need unsandboxed execution from Codex; sandboxed import can hang.
- Git may not be on PATH in this Windows environment.

## Common Commands

Run from `<repo>/sipi_harness`:

```powershell
npm run build:graph
npm run init:knowledge -- --case-name my_case --request "describe the design request"
npm run register:knowledge
npm run wiki:ops
npm run lint:wiki
npm run serve
npm run refresh:all
npm run smoke:kicad-mcp
```

For task-specific commands, inspect `sipi_harness/package.json` and the relevant output manifest before running anything.
