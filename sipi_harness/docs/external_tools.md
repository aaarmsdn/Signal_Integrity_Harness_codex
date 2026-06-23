# External Tools and References

This harness integrates with EDA tools through documented public APIs, local
command-line tools, or optional MCP adapters. The repository does not vendor
commercial tools, licenses, proprietary examples, or third-party source bundles.

## LLM Wiki / Knowledge Graph Pattern

- This harness uses an LLM wiki pattern for accumulating SI/PI design strategy
  knowledge before generating geometry or simulation benches.
- Reference: [karpathy LLM wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
- Reference implementation: [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki).
- Harness-specific rule: the wiki stores reusable design knowledge and source
  provenance. Tool execution policy belongs in `CODEX.md`, skills, docs, and
  config files, not in wiki pages.

## KiCad

- Primary integration: KiCad project/board files and `kicad-cli`.
- Reference: [KiCad Command-Line Interface](https://docs.kicad.org/9.0/en/cli/cli.html).
- Optional integration: KiCad MCP servers may be used by an agent for interactive
  board/schematic operations. Treat MCP servers as local adapters; verify their
  source, version, and license before relying on them in a shared workflow.

## Ansys AEDT / PyAEDT / PyEDB

- Primary integration: PyAEDT and PyEDB scripts that create/open AEDB/AEDT,
  assign HFSS 3D Layout ports, solve, and export Touchstone.
- Reference: [PyAEDT documentation](https://aedt.docs.pyansys.com/).
- Source repository: [ansys/pyaedt](https://github.com/ansys/pyaedt).
- Example repository: [ansys/pyaedt-examples](https://github.com/ansys/pyaedt-examples).

## Keysight ADS

- Primary integration: ADS Design Environment Python API and ADS Python runtime.
- Reference: [ADS Design Environment Python API documentation](https://edadownload.software.keysight.com/eedl/API_Doc/designenvironment/620/html/index.html).
- Additional reference: [ADS 2025 Release Notes](https://docs.keysight.com/display/engdocads/ADS%2B2025%2BRelease%2BNotes), which documents the ADS Python Console entry point.

## Document Parsing

- Baseline integration: PyMuPDF and pypdf for tier-0 page evidence, rendered
  page snapshots, and focused figure extraction.
- Preferred source-intake integration: Docling/DocLang for layout-aware
  extraction of complex PDFs/books into section, table, figure, equation, and
  image candidates.
- Reference: [Docling project](https://github.com/docling-project/docling).
- Harness-specific rule: parser output is evidence candidate data only.
  Compliance limits and design rules still require source-tier review before
  promotion into typed wiki cards or `design_strategy.yaml`.

## Licensing and Redistribution

- Users must install and license KiCad, Ansys AEDT, and Keysight ADS separately.
- Do not commit commercial solver databases, ADS workspaces, proprietary board
  files, vendor specs, books, or generated datasets unless redistribution rights
  are explicit.
- Keep machine-specific paths in `configs/tool_profiles.example.yml` copies,
  ignored local config files, or environment variables.

## Adapter Policy

Tool adapters should:

- Accept explicit input/output paths.
- Write summary JSON and logs.
- Report tool version when possible.
- Validate generated artifacts rather than trusting API return values.
- Fail with actionable messages when a tool is missing, unlicensed, or returns
  incomplete data.
