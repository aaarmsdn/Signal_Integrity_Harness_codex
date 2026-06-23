# SI/PI Harness Agent Handoff

Short startup file for Codex is `<repo>/CODEX.md`. This file
keeps deeper engineering rules that should apply to any future SI/PI task.

Do not assume the next task is related to any previous case. Treat each package,
PCB, interposer, connector, cable, memory interface, high-speed I/O, PDN, or
custom channel request as a fresh spec-driven flow.

## Start Here

Work from:

```powershell
cd <repo>
```

Read first:

- `<repo>/CODEX.md`
- `<repo>/README.md`
- `<repo>/sipi_harness/package.json`
- `<repo>/sipi_harness/spec_evidence_contract.md`
- `<repo>/sipi_harness/wiki/purpose.md`
- `<repo>/sipi_harness/wiki/schema.md`
- `<repo>/sipi_harness/docs/agent_lessons.md`
- Any manifest under the active `outputs/<case>/` folder

## Current Structure

- Main harness: `<repo>/sipi_harness`
- Wiki/graph app: `<repo>/sipi_harness/app`
- Wiki source pages: `<repo>/sipi_harness/wiki` for design strategy, not tool execution logs
- Wiki operating files: `purpose.md`, `schema.md`, `index.md`, `overview.md`, and `log.md`
- Obsidian vault export: `<repo>/sipi_harness/obsidian_vault`
- Optional local KiCad MCP config: `<repo>/.codex-kicad-mcp.toml`
- Optional local PyAEDT MCP config: `<repo>/.codex-pyaedt-mcp.toml`
- Case outputs: `<repo>/outputs`

## General Verification Rules

These are hard rules for future package/channel tasks across different SI/PI
applications:

0. Start with intake questions before choosing the design run mode:
   - Ask for missing design inputs that materially affect the result:
     governing spec/version/path, interface, topology, lane count, data rate,
     channel length, stackup, materials, copper, impedance target, via rules,
     pin/ball/bump/connector map source, compliance metrics, loading networks,
     masks, models, target tool versions, and expected artifacts.
   - Then ask whether optional source data will be added. Use
     `sipi_harness/wiki/raw/datasheet/`, `sipi_harness/wiki/raw/papers/`,
     `sipi_harness/wiki/raw/user_notes/`, `sipi_harness/wiki/raw/web_research/`,
     or case-local `outputs/<case>/knowledge_intake/user_references/`.
   - If the user adds PDFs, Office files, HTML, images, Markdown/text, CSV,
     XML/DocLang, LaTeX, email, or other Docling-supported sources, run
     `npm run setup:docling` once and then
     `npm run ingest:docling -- --case-dir <case-dir> --source-tier <tier> <source>`.
     Treat Docling output as candidate evidence until reviewed.
   - Only after those questions choose the design run mode: Stage Review,
     End-to-End Goal, or Single-Pass Design.
   - This is a hard stop. If the user has not answered the source-intake and
     run-mode questions, ask and wait. Do not default to End-to-End mode, create
     outputs, install dependencies, search the web, load stage-specific skills,
     or start Strategy/Layout/Solve/Bench work from the first design request.
     Keep this separate from execution mode: `dry_run` and `execute` control
     whether tools launch, not how stage pauses/revision loops behave.
1. Define the testbench before drawing or simulating:
   - Which spec clause, table, mask, equation, or measurement method is being tested.
   - Source, victim, aggressor, termination, capacitance, return/reference,
     data rate, frequency, and operating mode.
   - Expected final artifact: schematic, netlist, dataset, report, DDS,
     Touchstone, AEDT project, PCB project, or manifest entry.
   - A wiki-derived `design_strategy.yaml` and design strategy PDF under `outputs/<case>/strategy/`
     before PCB/package geometry is generated.
   - A `spec_metric_coverage` table or equivalent section that inventories all
     discovered requirement families from the governing source. Do not let the
     user's short prompt narrow the compliance search. Scan for frequency-domain
     S-parameters/transfer functions, impedance/TDR, crosstalk, skew/timing,
     jitter, transient waveform/eye/mask, BER/bathtub/contour, loading/source/
     receiver models, PDN/rail limits where applicable, and required reports.
     Each row must be mapped to an implemented bench, proxy-only check,
     not-applicable rationale, or blocker.
2. Build knowledge intake before drawing:
   - For each new design request, run or emulate `npm run init:knowledge` to
     create a case-local `knowledge_intake/` folder.
   - Search the internet for credible, current design-strategy sources related
     to the interface, package, PCB, PDN, channel, connector, or I/O task.
     Store URLs, access dates, source types, summarized claims, design rules,
     verification implications, and cautions in the web research registry.
   - Register user-provided or user-approved specs, books, datasheets, app
     notes, and internal notes in the user reference registry. Keep source
     documents local or case-local when copyright or access rights are unclear.
   - Raw source group hits are metadata only. If staged raw sources match the
     request, run `npm run report:wiki-strategy -- --case-dir <case-dir> --request-file <request.txt> --auto-ingest-sources`
     or explicitly run Docling/spec extraction before layout. A strategy report
     with `docling_hit_count=0` and only `Raw Source Group: ...` hits has not
     used document contents yet.
   - Raw source files and Docling extraction outputs are not committed to Git.
     They are generated per case under `outputs/<case>/knowledge_intake/` or
     `outputs/<case>/spec_evidence/`; if those folders are absent, source
     content was not ingested.
   - Repo wiki subfolders are scaffolds until populated with reviewed typed
     cards. README-only folders such as `design_rules/`, `constraints/`, and
     `stackups/` are not reusable engineering evidence. Do not cite a raw
     source group, empty folder, or folder name as the reason for a route,
     stackup, impedance target, or benchmark choice.
   - When `spec_evidence/spec_candidates.json` exists, the strategy report must
     show `spec_evidence_hit_count > 0`; otherwise the governing PDF extraction
     was stored but not fused into the strategy.
   - If a matching governing PDF or raw source group exists but
     `docling_hit_count=0` and `spec_evidence_hit_count=0`, stop before
     PCB/package generation. Run Docling/spec extraction/fusion or mark the
     Strategy stage blocked. Raw-source group names are metadata, not design
     evidence.
   - Fuse web research plus user references into the LLM wiki strategy input.
     The pre-PCB strategy report must cite the intake status and should not be
     based on existing wiki pages alone for a new application/spec.
   - After wiki changes, run `npm run wiki:ops` and `npm run lint:wiki` so the
     index, overview, operation log, and health report stay current.
   - If the engineer wants Obsidian graph browsing in a fresh clone, run
     `npm run export:obsidian` after rebuilding the graph, or run
     `npm run refresh:all` to rebuild registrations, graph, wiki ops, and the
     ignored `sipi_harness/obsidian_vault/`. Do not treat a missing
     `obsidian_vault/` folder as a design blocker; it is a generated view, not
     source data. Obsidian export may run in a background/subagent task after
     the graph inputs are stable.
   - Tool-stage subagents are opt-in, not the default. Use them only for
     bounded file-in/file-out tasks after the main agent has frozen exact input
     paths and stage goals. The main agent should handle stateful EDA repair
     loops itself, especially routing-violation repair, HFSS setup/sweep and
     Touchstone export debugging, and ADS connectivity debug. Subagents return
     artifacts and logs; they do not change run mode, invent missing limits,
     substitute proxy S-parameters, or claim compliance.
3. Read and preserve spec evidence before drawing:
   - Extract relevant PDF text, tables, figure captions, pin/ball maps, masks,
     equations, and loading diagrams into `outputs/<case>/spec_evidence/`.
   - Run the PDF dependency gate first: `npm run setup:pdf-python` from
     `sipi_harness/`. This installs/checks PyMuPDF so rendered page PNGs can be
     produced for visual figure review.
   - Record page, section, figure, and table identifiers in the case strategy
     and manifest.
   - If a map, pinout, ball map, escape diagram, mask, or loading network is
     only present as a PDF figure, inspect the figure itself before creating
     coordinates or connectivity. Use PDF text extraction where possible, then
     cross-check with visual/vector/image inspection of the page or cropped
     figure. Do not use a remembered or "similar" map without marking it as a
     proxy.
   - A figure-derived map must save a reviewable evidence bundle containing
     the source PDF path, page number, section/table/figure ID, extraction
     method, raw extracted rows or coordinates, a figure snapshot/crop path
     when available, normalization assumptions, and reviewer status. If that
     evidence is incomplete, the design may proceed only as an explicitly
     labeled proxy.
   - If the governing spec does not provide a bump/ball/pin map, create a
     case-local synthetic map before routing. Save the generated rows/columns,
     pitch, side/module placement, lane mapping, and assumptions under
     `outputs/<case>/routing/` or `outputs/<case>/spec_evidence/`. Mark the map
     as `source_type: synthetic`; use it for topology/proxy exploration unless
     the spec explicitly permits arbitrary endpoint placement.
4. Do not treat a quick S-parameter proxy as a spec-equation check. If the
   specification defines a voltage transfer function, impedance target, mask,
   jitter, power-sum crosstalk, droop, ripple, or other derived metric,
   implement that exact metric and label proxy checks as proxies.
   If the spec defines an eye diagram, eye mask, BER contour, bathtub, jitter,
   or other transient/statistical requirement, it must appear in the strategy
   coverage matrix and in the bench plan. A passing insertion-loss/crosstalk
   plot alone cannot close compliance for that source.
   If no spec-specific benchmark has been extracted yet, still generate a
   spec-neutral S-parameter bench/report from the Touchstone with
   `npm run bench:sparameter`. Plot insertion loss, return loss, and crosstalk
   where applicable, and record it as sanity/proxy evidence, not compliance.
   If spec-specific VTF, XT, loading, eye/mask, BER, bathtub, or jitter
   evidence exists, do not use `bench:sparameter` as the Bench stage result.
   Implement the exact benchmark or mark Bench blocked as
   `blocked_missing_spec_bench_implementation`; S-parameter fallback is only an
   explicit diagnostic supplement in that case.
   ADS failure is a stage blocker, not a reason to create proxy datasets. Keep
   repairing the real ADS workspace/netlist/dataset/report until the required
   bench exists, or stop with a blocker and stage report.
5. For any ratio-based metric, identify the physical numerator and denominator
   before coding:
   - Source node versus channel input node.
   - Victim receiver node versus intermediate node.
   - Single-ended versus differential convention.
   - Linear magnitude, voltage dB, power dB, or integrated/power-sum form.
6. For crosstalk, do not assume "worst single aggressor" is the compliance
   value. Check whether the spec requires worst aggressor, sum, power sum,
   integrated noise, near-end/far-end separation, or a defined aggressor count.
7. ADS or other circuit schematic generation must be validated twice:
   - Visually in the GUI when practical for wrong wires, overlapping labels,
     broken nodes, wrong component type, and wrong Touchstone filename.
   - By exported netlist for actual nodes, source polarity, reference nodes,
     and component connectivity.
8. Source polarity and node labels are easy to get wrong:
   - Do not rely on assumed pin ordering without checking exported netlist.
   - If wire routing causes source ground to touch the driven node, separate
     the components and use net labels or route the ground stub away from the
     source path.
9. Use explicit components for spec loading when the spec names explicit
   components. Do not replace a required R/C/RLC loading network with a generic
   termination symbol unless it is proven equivalent.
10. Multiport Touchstone details:
   - Confirm port count, port order, reference impedance, frequency units, and
     terminal mapping before analysis.
   - Put files in the workspace's expected data folder unless the schematic
     uses a verified absolute path.
   - Avoid accidental filename prefixes or quoting styles not accepted by the
     simulator.
11. Eye/mask checks must be explicit:
   - Compute UI from the active data rate.
   - Use the simulator's BER contour/width/height outputs when the spec defines
     a BER target.
   - Report height and width separately; overall mask passes only if all
     required dimensions pass on every required victim or lane.
12. Package/PCB geometry checks are a required gate before EM solve:
   - Do not route package/PCB channels by LLM-invented waypoints. When endpoints
     come from a ball map, pad map, connector pinout, or pin table, use A* or a
     deterministic tool-native router and save the route request/result under
     `outputs/<case>/routing/`.
   - If no endpoint map exists, generate the bump/ball/pad map first and route
     from that saved artifact. The route result must reference either the
     extracted tier-0 map or the synthetic map artifact; never route from
     unstated coordinates.
   - Check pad, via, ball, pin, and launch geometry for overlap and minimum
     edge clearance using actual generated coordinates and sizes.
   - Check trace-to-trace corridor clearance and same-layer crossing risk;
     do not assume lane ordering or autogenerated fanout is interference-free.
   - Prefer 45-degree diagonal routing for high-speed channels and avoid
     unnecessary 90-degree bends. Use 90-degree corners only when explicitly
     required by escape geometry, manufacturing rules, or the design strategy.
   - Do not disable diagonal routing to make a failed route pass. If a diagonal
     route crosses or shorts, repair lane order, fanout, layer assignment,
     keepouts, spacing, endpoint pairing, or stackup constraints while keeping
     `allow_diagonal: true`. Turning it off requires an explicit
     manufacturing/spec reason and engineer approval.
   - A route result with `allow_diagonal: false`, missing route settings, or
     avoidable orthogonal-only/90-degree high-speed routing is not reviewable
     unless the strategy records a manufacturing/spec reason and the engineer
     approved that exception. Keep diagonal routing enabled during repair.
   - Reference-plane coverage is mandatory before HFSS. Local GND launch tabs,
     port tabs, or short reference patches do not replace a continuous adjacent
     return path along the channel. If a repair route removes the assigned
     reference plane/layer or makes the design signal-only, reject the layout
     and repair PCB/package generation before import.
   - Minimize routed centerline length first. Use endpoint/lane ordering and
     allowed-layer candidates that reduce total route length and obvious
     crossings before adding any length-matching meanders.
   - If a target impedance is known, estimate initial KiCad width/spacing from
     stackup/material before routing and record the target, estimate method,
     applied width/spacing, Dk/Df, reference layer, and any pitch/clearance
     clamp in the route result and manifest. Treat this as pre-layout guidance,
     not compliance evidence.
   - Always run
     `npm run check:kicad-geometry -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_same_layer_geometry.json --manifest <case-dir>\manifest.json`
     before HFSS handoff. A PASS result is required for a valid EM candidate.
     Any different-net same-layer crossing, same-layer short, trace-to-pad/via
     short, or pad/via overlap is a hard blocker unless explicitly reported as
     proxy/blocked.
   - In End-to-End Goal Mode, these violations must trigger an in-stage repair
     loop before stopping: rerun A* with different lane order, diagonal routing,
     updated keepouts, alternate allowed signal layer, fanout revision, or
     strategy-approved spacing/stackup changes. Stop only after the repair
     attempts are recorded and no valid route exists under current constraints.
   - In Single-Pass Design Mode, still repair invalid stage artifacts. The
     "single pass" limitation applies to design revision after final metrics,
     not to broken geometry, missing Touchstone, invalid ports, or failed ADS
     connectivity.
   - Compute actual routed centerline length per channel, not nominal endpoint
     spacing, and convert length skew into delay/UI using the active data rate
     and an explicit propagation-delay assumption.
   - Store these checks in `outputs/<case>/manifest.json` and the design
     report. If any check is missing or failing, the layout stage is not ready
     for solver handoff.
   - After KiCad/package generation, render a review image with
     `npm run render:kicad-preview -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_layout_preview.png --manifest <case-dir>\manifest.json`.
     Show this image to the engineer in Stage Review Mode before HFSS handoff.
     The preview image is required for human review, while DRC, route records,
     and geometry gates remain the machine-readable evidence.
13. Pre-PCB strategy reporting is required:
   - Use `sipi_harness/scripts/generate_wiki_strategy_report.py` or the
     equivalent case generator hook before layout generation.
   - The YAML and report must summarize wiki knowledge used, spec evidence status,
     intended geometry checks, solver handoff, ADS/circuit benches, and final
     report outputs.
   - Store the PDF, Markdown, and JSON report paths in the active manifest.
14. KiCad to HFSS 3D Layout port handoff must be explicit:
   - During KiCad/package generation, emit `simulation/hfss3dlayout_port_intents.json`.
   - Each port intent must include port name, signal net, reference net/layer,
     positive launch coordinate or pad/ball, reference geometry selector,
     expected impedance, and expected order.
   - The HFSS import script must read port intents and create AEDB polygon-edge
     circuit ports by default (`--port-method edb_polygon_edge`). Coordinate
     `circuit` ports or `pin` ports require explicit override and manual/tool
     evidence because imported coordinates can be misplaced after AEDB import.
   - Save the AEDT project, reopen it, and verify port count/order before solve.
   - When opening an AEDB, do not force `design="PCB"` unless the import summary
     says the imported design is actually named `PCB`. Let AEDT open the imported
     cell or pass the recorded imported design name. If `app.port_list` is empty
     after reopen, stop before solve; a successful `analyze_setup()` on an empty
     or wrong design is not a valid EM result.
   - Do not infer ports later from arbitrary line ends when the board generator
     can emit pad/launch metadata up front.
15. HFSS solve setup must come from strategy:
   - Compute Nyquist as `data_rate / 2`.
   - Cover at least `5 * Nyquist` unless the spec requires more.
   - Use 10-30 points only for smoke/import checks.
   - Use 101-401 points for engineering channel checks.
   - Use segmented/adaptive finer sweeps around resonances, anti-resonances,
     crosstalk peaks, and spec limit frequencies.
   - Record whether the run is smoke, engineering estimate, or compliance.
   - In Stage Review Mode, do not run HFSS solve until
     `npm run prompt:stage-review -- --stage hfss ...` has displayed the setup
     and the engineer approves it.
16. Keep status documents current:
   - Keep `CODEX.md` and top-level READMEs general.
   - Put case-specific status in `outputs/<case>/manifest.json`, generated
     reports, and case strategy files.
   - Keep reusable commands spec-neutral. Put example or legacy case commands
     under a `case:<name>:` prefix in `sipi_harness/package.json`.
   - Do not leave old workspace names documented as current when a newer
     verified workspace exists.

## Goal-Mode Completion Contract

When using Codex `/goal` for this workspace, use this completion contract:

```text
Do not stop at partial PCB or solver setup. For each SI/PI design request:
1. Compile spec/target input into a Design Strategy IR before tool execution.
2. Initialize knowledge intake, then collect web research and user-reference evidence.
3. Generate `strategy/design_strategy.yaml` and a pre-PCB wiki design-strategy PDF, then store both in the case manifest.
4. Generate a complete project bundle, not only a single board or netlist file.
5. Run layout/design checks and record violations/unconnected items.
6. Generate solver port intent before solving.
7. Run EM/circuit simulation until the expected extracted data exists.
8. Verify extracted data dimensions, port order, units, and metadata.
9. Produce a manifest and evidence-linked report.
```

The PCB/package design stage is complete only when the active case folder has:

```text
project files
board/layout files
schematic or source connectivity where applicable
reports/design_check or DRC result
knowledge_intake/web_research/*
knowledge_intake/user_references/*
knowledge_intake/wiki_fusion/*
strategy/design_strategy.*
strategy/pre_pcb_wiki_design_strategy_report.pdf
strategy/design_strategy.yaml
simulation/port_intents.*
manifest.json
```

The EM solver stage is complete only when the active case folder has:

```text
solver project/database
extracted S-parameter or field result
solver setup summary
port-order metadata
report artifact
manifest.json updated with solver status
```

The circuit/spec-check stage is complete only when the active case folder or
workspace has:

```text
verification schematic or netlist
input data copied or resolved by the simulator
dataset or simulation log
metric extraction script/output
plots or DDS/report views
pass/fail report with exact equations and limits
```

## Tool Notes

KiCad:

- Prefer complete project bundles over isolated board files.
- Run DRC and record both violations and unconnected items.
- Preserve explicit stackup, net names, constraints, and port/launch metadata.
- Generate and show a layout preview image before HFSS handoff in Stage Review
  Mode. Record the PNG path in the manifest.

HFSS 3D Layout / PyAEDT:

- Preferred PCB handoff is documented layout data -> AEDB/HFSS 3D Layout.
- Always verify imported stackup, reference planes, components, nets, and
  primitives before solving.
- Port intent should include signal net, reference net/layer, port type,
  positive launch coordinate or pad/ball, reference geometry selector,
  impedance, and expected order.
- Pass the intended AEDT version explicitly to import, solve, and export
  commands. Treat a 2024/2025/2026 version mismatch as a blocker unless the
  engineer explicitly accepts compatibility risk.
- Do not trust `analyze_setup()` alone. A valid EM handoff requires a non-empty
  Touchstone with expected port count, order, and frequency coverage.
- For HFSS 3D Layout sweeps, a visible `Sweep1` is not enough. Verify the sweep
  has a real frequency range row and exports the requested sweep, not only
  `Last Adaptive`. Prefer `Hfss3dLayout.create_linear_count_sweep(...)`; for
  native ScriptEnv fallback, use the HFSS 3D Layout `Sweep3DLayout` template
  with `Sweeps.Data = "LINC <start>GHz <stop>GHz <points>"`. Do not rely on
  generic `RangeStart`/`RangeEnd` properties alone.
- If PyAEDT export and native AEDT `ExportNetworkData` both fail after a
  truthy solve, classify the result as non-exportable ports or missing network
  data. Rebuild the port method or block EM; do not send it to compliance.
- Do not repair an HFSS export failure by weakening the electrical layout.
  Reroute only if the new route preserves the strategy stackup, continuous
  reference plane, port-reference model, impedance intent, and diagonal routing
  rule. A route without a real reference plane must be blocked before HFSS even
  if the geometry preview looks clean.
- The EM stage is not complete until a verified non-empty Touchstone exists.
  If export fails, keep repairing the real layout/import/port/solve path until
  the required artifact exists, or stop with an explicit blocker. Do not
  generate synthetic S-parameters to unblock ADS.

ADS:

- Use ADS 2025 Update 2 or newer.
- Use ADS Python with `HPEESOF_DIR` set to the installed ADS root.
- Preferred ADS runtime is
  `C:\Program Files\Keysight\ADS2026_Update2\tools\python\python.exe` with
  `HPEESOF_DIR=C:\Program Files\Keysight\ADS2026_Update2`.
- ADS Design Environment API calls may need unsandboxed execution in Codex.
- After schematic generation, check the GUI and exported netlist.
- Keep ADS schematic construction and netlist execution separate. For a
  spec-defined compliance bench, the expected completion state is
  `schematic_plus_netlist`: an ADS workspace and schematic are generated, the
  Touchstone is copied into the workspace `data/` folder, the schematic netlists,
  and the simulator dataset/plots come from that bench. A passing `.ckt` run
  without an equivalent inspectable schematic is only `netlist_only_diagnostic`
  and cannot close Bench unless the engineer explicitly requested netlist-only
  output.
- If ADS DE symbol placement, OA locks, or schematic netlisting fail, keep the
  stage blocked as `blocked_missing_schematic` or `blocked_invalid_schematic`
  with logs instead of silently switching to netlist-only execution.
- For ChannelSim eye/BER benches, run the ADS-DE exported schematic netlist
  promoted from `reports/*.netlist.log`, not a reduced hand-written `.ckt`.
  The accepted netlist must preserve Eye Probe settings for density,
  BERContour, width/height-at-BER, and ultra-low-BER simulation. If those
  settings or the resulting contour variables are absent, repair the ADS bench
  before reporting.
- For a new ADS installation, broken workspace, or uncertain symbol/API state,
  run `npm run bench:ads-workspace -- --workspace <case-dir>\bench\ads_bench_wrk --overwrite`
  before building the case bench. This creates SnP, loaded AC, and ChannelSim
  eye bench checks plus `reports/*.netlist.log` audits. Use them as baselines
  only; replace source/load/model/equation details from the active strategy
  before claiming compliance.
- Smoke benches are not compliance results. Generated case/demo workspace,
  cell, and netlist names must not include `template`; use names such as
  `ads_bench_wrk` and `channelsim_full_8lane_eye`. For a lane-count N
  compliance bench,
  use the full S(2N)P Touchstone, run every required victim lane, and include
  all N-1 aggressors when the spec defines crosstalk or eye-with-aggressor
  conditions. Never close an x8 Bench stage with a 3-lane `.s6p` example.
- Dataset extraction should use simulator output variables directly when
  available, rather than reconstructing compliance values from unrelated data.
- If a governing spec bench is unavailable, create the fallback SnP benchmark
  workspace/report with `npm run bench:sparameter -- --workspace <case-dir>\bench\sparameter_wrk --touchstone <channel.sNp> --overwrite`.
  The generated report is a portable sanity check for insertion loss, return
  loss, and crosstalk, not a replacement for the final spec equations.
- Treat legacy microstrip ADS scripts as examples only. Do not use
  `create_ads_channel_workspace.py`, `create_ads_channel_schematic.py`, or
  `run_ads_channel_sim.py` as the generic multi-lane/spec bench implementation.
- Do not run ADS/bench from synthetic or proxy S-parameters unless the engineer
  explicitly asks for a non-compliance diagnostic. The normal flow requires a
  verified HFSS or measurement Touchstone.
- In Stage Review Mode, do not run ADS/bench verification until
  `npm run prompt:stage-review -- --stage ads ...` has displayed the benchmark
  setup and the engineer approves it.

Reporting:

- Every stage should emit a PDF or Markdown report with source artifact paths,
  assumptions, equations, limits, tables, plots, and pass/fail status.
- Stage report emission is independent of run mode. At every stage boundary,
  run `npm run report:checkpoint -- --case-dir <case-dir> --stage <stage>
  --status completed|proxy|blocked|failed` before advancing. End-to-End and
  Single-Pass modes still save stage PDFs; they just do not pause for review
  unless blocked.
- Reports must state whether a result is a proxy, an engineering estimate, or
  the exact spec-defined measurement.

Context continuity:

- Long EDA runs often trigger context compaction. Before and after each stage,
  update `outputs/<case>/agent_state.md` or `outputs/<case>/agent_state.json`
  with the active case path, run mode, current stage, required artifacts, exact
  next command, tool/Python paths, blockers, and no-proxy rules.
- After compaction or a new session, read `CODEX.md`, this file,
  `sipi_harness/docs/workflow.md`, the case manifest, the latest stage report
  manifest, and agent state before continuing.
- Do not use `llm-optimizer` in the baseline harness flow. Use it only when the
  engineer explicitly asks for an optimization loop after the baseline
  strategy, layout, EM, and bench handoffs are valid.

Case file discipline:

- Do not mutate files under `sipi_harness/examples/` while running a case.
  Copy/adapt example logic under `outputs/<case>/automation/` or create a new
  reusable script as a deliberate repository change.

## Known Portable Commands

From `<repo>/sipi_harness`:

```powershell
npm run build:graph
npm run wiki:ops
npm run lint:wiki
npm run serve
npm run refresh:all
npm run smoke:kicad-mcp
```

For case-specific commands, inspect the active case manifest and
`sipi_harness/package.json`. Do not run a case-specific command unless it
matches the current task and target specification.
