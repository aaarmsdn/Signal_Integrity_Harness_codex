# SI/PI Engineering Harness

This harness starts with an LLM wiki and knowledge graph for SI/PI engineering.
It is intentionally file-based so the knowledge base, strategy records, tool
outputs, and reports can be reviewed, versioned, and connected to KiCad, PyAEDT,
and Keysight ADS workflows.

![SI/PI Engineering Harness Overview](docs/assets/harness_overview.png)

## What Is Included

- `wiki/`: human-readable SI/PI wiki pages.
- `wiki/purpose.md`: goals, scope, and key questions for the wiki.
- `wiki/schema.md`: page conventions and ingest/query/lint rules.
- `wiki/index.md`, `wiki/overview.md`, `wiki/log.md`: generated operating files for navigation, summary, and history.
- `data/sources.json`: curated source records, extracted concepts, claims, and relationships.
- `data/knowledge_graph.json`: generated graph consumed by the viewer.
- `scripts/build_graph.mjs`: builds the graph from curated source records.
- `scripts/serve.mjs`: serves the static graph viewer locally.
- `scripts/`: generation, export, solver, ADS, extraction, and report automation.
- `obsidian_vault/`: exported Markdown vault for Obsidian graph/backlink use.
- `app/`: browser UI for searching and visualizing the graph.

The structure follows a GraphRAG-style pattern: documents are decomposed into
concepts, claims, relationships, and communities with source provenance.

## Quick Start

```powershell
cd <repo>\sipi_harness
npm install
npm run smoke:sample
npm run build:graph
npm run wiki:ops
npm run lint:wiki
npm run serve
```

Then open:

```text
http://127.0.0.1:8765/app/
```

If a local server is not needed, open `app/index.html` directly. The graph data
is also generated into `app/graph-data.js` for file-based viewing.

## Run the Harness Dry-Run

Use the sample case to verify the repository on a new machine without requiring
EDA licenses:

```powershell
cd <repo>\sipi_harness
npm run harness:dry-run -- --config examples\sample_case\config.yml --case-dir outputs\sample_case
```

This validates the sample input contract and writes:

- `outputs/sample_case/manifest.json`
- `outputs/sample_case/reports/harness_run_summary.md`
- `outputs/sample_case/logs/harness.log`

For a real case, copy `configs/default.yml`, update the paths and limits, then
run the same dry-run before launching KiCad, HFSS 3D Layout, or ADS stages.

## Spec-Driven Tool Flow

For any new application:

1. Register the spec/source documents and relevant design references.
2. Create a case folder under `outputs/`.
3. Write a design strategy that defines the final verification benches before
   generating geometry.
4. Generate complete KiCad/package/interconnect artifacts where applicable.
5. Export to the selected solver and generate explicit port-intent metadata.
6. Run EM extraction until a verified Touchstone or solver result exists.
7. Build ADS or equivalent circuit benches from the strategy.
8. Extract metrics directly from datasets and write evidence-linked reports.

Case-specific scripts may exist in this repository as examples or active
workflows. Treat them as examples unless the active case manifest and strategy
explicitly select them.

The strategy stage is spec-neutral. It first extracts
`design_strategy.validation_benches.spec_requirements` from the governing
source evidence, including any impedance, insertion/return loss, crosstalk,
transfer-function/loading, eye/mask, BER/contour, bathtub, skew, or jitter
requirements it can find. Tool-specific adapters such as ADS profiles are
attached only after those source-derived requirements exist; adapters must not
replace the required bench list. If a required metric family is detected but no
tool adapter implements it, the Bench stage remains blocked instead of falling
back to a proxy result.
When no custom adapter exists, generic implementations may still run
source-backed checks that use standard artifacts such as geometry, TDR, route
delay, or Touchstone S-parameters. Metrics that require a specific
circuit/statistical topology remain explicit `blocked_benches`.
Those blocked benches remain reportable and can seed an on-demand adapter:
`npm run plan:bench-adapter -- --strategy <case-dir>\strategy\design_strategy.yaml`.

## Productization Docs

- `docs/input_contract.md`: required files, optional files, formats, units,
  naming, and common input errors.
- `docs/architecture.md`: separation between core, examples, adapters, configs,
  and generated outputs.
- `docs/adapting_to_new_case.md`: checklist for applying the harness to a new
  board/package/interface.
- `docs/workflow.md`: stage graph, tools, outputs, and failure conditions.
- `docs/validation_rules.md`: pass/fail gates, metric extraction, and waivers.
- `docs/human_checkpoints.md`: review points that require SI/PI judgment.
- `docs/external_tools.md`: LLM wiki, KiCad, PyAEDT, and ADS references plus
  adapter policy.
- `configs/default.yml`: reusable editable configuration template.
- `configs/tool_profiles.example.yml`: local EDA tool profile template.
- `examples/sample_case/`: minimal dry-run case and expected outputs.

## Reporting

The stage report generator can write PDF evidence for a completed case:

```powershell
cd <repo>\sipi_harness
npm run report:stages -- --case-dir <case-dir> --ads-workspace <ads-workspace-dir>
```

Expected reports:

- PCB/package design report with geometry preview and checks.
- EM solver report with project paths, Touchstone metadata, and S-parameter plots.
- Circuit/spec report with compliance tables, dataset-derived plots, and pass/fail status.

## Portability

The scripts are shareable, but EDA tool installations are local. On a different
computer, update paths in `package.json` or call the underlying scripts with
explicit tool paths for:

- KiCad CLI.
- AEDT / PyAEDT Python environment.
- ADS root and ADS Python.

Do not assume generated solver databases, Touchstone files, ADS datasets, or
specification-derived content can be freely redistributed. Check the applicable
license, NDA, and design-IP constraints first.

## Next Integration Points

- KiCad MCP: add board/schematic extraction as source documents and graph entities.
- PyAEDT: add HFSS/Q3D simulation templates as executable tool nodes.
- Keysight ADS: add Touchstone, channel, and PDN analysis runs as evidence nodes.
- LLM agent: use `data/knowledge_graph.json` as retrieval context with local/global graph search.
