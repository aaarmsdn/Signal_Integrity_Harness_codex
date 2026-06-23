---
graph: false
id: raw_extracted_evidence_readme
title: Raw Extracted Evidence
status: active
---

# Extracted Evidence

Store reviewed evidence snippets here after extracting from PDFs, books, specs,
or app notes.

Each record should preserve:

- source ID
- source path or URL
- source hash when local
- page number
- section/table/figure/equation identifier
- extracted text or structured value
- screenshot/crop path if available
- review status
- allowed usage

Numeric compliance values must stay here or in case-local `spec_evidence/` until
they are reviewed and promoted into a `spec_constraint` typed card.
