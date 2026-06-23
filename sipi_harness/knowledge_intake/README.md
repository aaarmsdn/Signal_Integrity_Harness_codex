# Knowledge Intake

This folder defines the reusable intake structure for new SI/PI design tasks.

For each new design request, the harness should collect two evidence streams
before PCB/package layout starts:

1. Web research: current, credible design strategy material found online.
2. User references: user-provided or user-approved specs, books, notes,
   datasheets, app notes, and internal documents.

The LLM wiki and case `design_strategy.yaml` are built from the combination of
those two streams plus the existing reusable wiki pages.

The repo-level `wiki/raw/datasheet/` folder is a local, ignored library for
user-provided specs and datasheets such as UCIe, HBM/JESD, PCIe, CXL, and
LPDDR. Treat it as a source library, not as the wiki itself. For a case, either
reference a file from `wiki/raw/datasheet/` in the case config or copy/link it under
`outputs/<case>/knowledge_intake/user_references/`, then extract reviewed
`spec_evidence/` before using numeric limits or figures.

Large PDFs, books, extracted chunks, and copyrighted source material should stay
local or case-local under `outputs/<case>/knowledge_intake/`. Do not commit them
unless sharing rights are explicit.

Use:

```powershell
cd <repo>\sipi_harness
npm run init:knowledge -- --case-name my_case --request "describe the design request"
```

Then fill the generated registries:

- `outputs/<case>/knowledge_intake/web_research/web_research_registry.json`
- `outputs/<case>/knowledge_intake/user_references/user_reference_registry.json`
- `outputs/<case>/knowledge_intake/wiki_fusion/wiki_fusion_input.json`

Reusable curated sources can be copied into the repo-level intake registries and
registered with:

```powershell
npm run register:knowledge
npm run build:graph
npm run export:obsidian
```
