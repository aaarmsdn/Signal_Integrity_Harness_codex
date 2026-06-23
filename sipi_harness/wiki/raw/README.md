---
graph: false
id: raw_staging_area_readme
title: Wiki Raw Staging Area
status: active
---

# Wiki Raw Staging Area

Use this folder for curated source material before it becomes a typed wiki card.
This is a staging area, not the final LLM wiki.

Important: putting a file here does not automatically make its contents usable
by the design agent. The harness uses raw files in three different levels:

1. `register:raw-sources` records that the files exist and groups them by
   folder. This creates source inventory metadata only.
2. `ingest:docling` converts selected files into Markdown/JSON/chunks. These
   chunks become candidate evidence after `register:docling`.
3. Reviewed evidence can then be promoted into typed wiki cards or case-local
   `spec_evidence`. Only this reviewed/promoted evidence may drive design rules
   or numeric compliance thresholds.

If a source appears only as a raw source group, it can help the agent discover
that a relevant local document exists, but it must not be treated as if the
document content has already been read.

Do not confuse the shared repository scaffold with a populated knowledge base.
The baseline repo intentionally ships README-only folders for typed cards and
ignored raw-source directories. Those folders are prompts for where evidence
will go; they are not design rules, constraints, stackups, or compliance
benchmarks. A design strategy should not advance to routing because a folder
named after an interface, package, or design topic exists. It may advance only
after request-relevant content is ingested, reviewed, and linked into
`design_strategy.yaml`, or after the missing evidence is explicitly recorded as
a blocker/proxy assumption.

Store short summaries, extracted snippets with provenance, source metadata, and
review notes here. Do not store full copyrighted PDFs, books, proprietary specs,
papers without redistribution rights, or large generated datasets here.

Copyright matters. Before using any source for the LLM wiki, check whether the
source can be copied, redistributed, summarized, or only referenced locally. The
shared repository should contain structure, metadata, reviewed short notes, and
source IDs, not copyrighted source dumps.

Recommended flow:

```text
wiki/raw/datasheet/ or external source
-> npm run register:raw-sources
-> Docling conversion into Markdown/JSON/chunks when supported
-> npm run register:docling
-> case-local spec_evidence/ extraction
-> wiki/raw/ curated notes
-> wiki typed cards
-> graph/Obsidian export
```

Docling conversion:

```powershell
cd sipi_harness
npm run setup:docling
npm run check:docling
npm run ingest:docling -- --case-dir outputs\my_case --source-tier tier_0 wiki\raw\datasheet\<interface>\<spec>.pdf
npm run register:docling
npm run refresh:all
```

Docling artifacts are candidate evidence only. Review page, table, figure,
equation, and source-tier metadata before promoting any value into a wiki card
or compliance threshold.

Folders:

- `web_research/`: curated web source summaries and URLs.
- `papers/`: paper metadata, reviewed summaries, and allowed extraction notes.
- `user_notes/`: engineer-written design notes and observations.
- `extracted_evidence/`: reviewed snippets, tables, equations, figure notes, and
  page references extracted from PDFs/books/specs.
- `source_registry/`: source IDs, tiers, access/licensing notes, and local path
  references.
