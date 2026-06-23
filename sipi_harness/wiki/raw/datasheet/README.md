---
graph: false
id: raw_datasheet_library_readme
title: Raw Datasheet and Specification Library
status: active
---

# Datasheet and Specification Library

This folder is a local, ignored library for user-provided governing
specifications, datasheets, standards, and package/interface documents.

Typical layout:

```text
wiki/raw/datasheet/
  interface_or_vendor_a/
  memory_or_package_standard_b/
  connector_or_module_standard_c/
  custom_internal_spec/
```

These files are **not** the LLM wiki. They are source material used to create
case-local `spec_evidence/` bundles and, when appropriate, small wiki
`source_card` records.

Rules:

- Keep copyrighted or restricted PDFs out of Git.
- Do not copy full spec text into wiki cards.
- Extract only the pages/tables/figures/equations needed for the active case
  into `outputs/<case>/spec_evidence/`.
- Numeric compliance limits may be used only after tier-0 evidence is extracted,
  linked to page/table/figure/equation IDs, and reviewed.

Example:

```powershell
npm run extract:spec-evidence -- --pdf wiki\raw\datasheet\<family>\<governing-spec>.pdf --out-dir outputs\my_case
```

Optional Docling conversion for layout-aware Markdown/JSON/chunk candidates:

```powershell
npm run setup:docling
npm run ingest:docling -- --case-dir outputs\my_case --source-tier tier_0 wiki\raw\datasheet\<family>\<governing-spec>.pdf
npm run register:docling
npm run refresh:all
```

The Docling output supports review and retrieval, but it is not automatically
trusted. Numeric limits, masks, loading networks, bump maps, and equations still
need tier-0 evidence review before use in compliance logic.
