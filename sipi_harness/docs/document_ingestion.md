# Document Ingestion and Chunking

The harness treats specifications, datasheets, books, application notes, and
web references as source material. Source material is not the LLM wiki itself.
It must be converted into reviewed evidence or reusable typed wiki cards before
it can drive design or compliance decisions.

## Ingestion Levels

1. **Source registration**
   - Record title, version, path or URL, source tier, access rules, and intended
     usage.
   - Do not copy copyrighted book/spec contents into Git.

2. **Layout-aware extraction**
   - Extract page text, table candidates, equation candidates, figure snapshots,
     and page images with provenance.
   - Preserve page number, section heading, table/figure caption, bounding box
     when available, and source hash.

3. **Semantic chunking**
   - Chunk by engineering meaning, not fixed character count alone.
   - Preferred units are section, subsection, table, figure, equation block,
     design rule, worked example, and validation procedure.

4. **Evidence review**
   - Numeric compliance values require reviewed tier-0 evidence.
   - Book or app-note chunks may suggest design heuristics, but must not become
     final pass/fail thresholds.

5. **Typed card promotion**
   - Promote only reviewed, reusable content into `wiki/` typed cards.
   - Preserve `source_ids`, source tier, page/section provenance, and
     `missing_information`.

## Chunking Policy

Avoid chunks that are only arbitrary pages or fixed-length text blocks. A useful
chunk should answer one of these questions:

- What design object does this describe?
- What constraint, equation, or validation metric does this define?
- What design knob does this rule change?
- What condition makes the rule applicable or invalid?
- What evidence would be needed before using this in compliance?

Recommended metadata per chunk:

```yaml
chunk_id: stable_id
source_id: source_book_or_spec
source_path: local_or_url
source_sha256: hash_when_local
page_start: 10
page_end: 12
section_path:
  - Chapter 3
  - Transmission Lines
chunk_type: design_rule | equation | table | figure | worked_example | background
topics:
  - impedance
  - return_path
claims:
  - text: Short extracted claim.
    evidence_status: candidate
relationships:
  - source: Return Path
    predicate: affects
    target: Crosstalk
    polarity: negative
review_status: unreviewed
```

## Docling / DocLang Ingestion Path

Docling is the preferred layout-aware ingestion backend when the source
contains complex tables, figures, multi-column text, or scanned pages. It is a
better fit than simple paragraph chunking for SI/PI books and specifications
because it can retain document structure such as reading order, tables,
formulas, and images.

Use Docling as an extractor and candidate-evidence generator, not as an
automatic source of truth:

```text
PDF/book
-> Docling document conversion
-> section/table/figure/equation candidates
-> case-local review queue
-> typed cards or spec_evidence
```

Docling/DocLang output should still pass the same review gates as PyMuPDF or
pypdf output. The harness must not promote unreviewed OCR/table output into a
compliance limit.

Install and check the optional backend:

```powershell
cd <repo>\sipi_harness
npm run setup:docling
npm run check:docling
```

Convert sources into candidate evidence artifacts:

```powershell
cd <repo>\sipi_harness
npm run ingest:docling -- --case-dir <case-dir> --source-tier tier_0 <path-to-spec.pdf>
npm run ingest:docling -- --out-dir <out-dir> --source-tier tier_1 <path-to-folder-or-url>
npm run register:docling
npm run refresh:all
```

The adapter writes:

- `<source_id>.docling.md`
- `<source_id>.docling.json`
- `chunks/<source_id>.chunks.json`
- `<source_id>.summary.json`
- `docling_ingest_manifest.json`

For Markdown/text/CSV/XML/LaTeX sources, the adapter falls back to plain-text
chunking when Docling cannot decode the file directly. The fallback tries common
UTF-8 and Korean encodings and records `conversion_status: text_fallback` plus
the original conversion error in the source summary. This keeps source intake
from silently disappearing because one text file used a local encoding.

`npm run register:docling` registers Docling source and chunk summaries into
`data/sources.json` for graph retrieval. `npm run refresh:all` then rebuilds the
knowledge graph, wiki operating files, and Obsidian vault.

Supported source types depend on the installed Docling version. The intended
harness set is PDF, DOCX, PPTX, XLSX, HTML, EPUB, images, Markdown/text, CSV,
email, XML, and LaTeX. Treat all converted chunks as candidate evidence until
reviewed.

## Fallback

The legacy `ingest_local_books.mjs` path performs text extraction and paragraph
chunking. Use it only for rough discovery or backlog creation. For engineering
strategy cards, prefer layout-aware extraction plus review.
