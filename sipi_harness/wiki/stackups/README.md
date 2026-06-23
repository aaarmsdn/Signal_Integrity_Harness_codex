---
graph: false
kind: wiki_control
---

# Stackup Profiles

This directory is intentionally empty in the shared repository baseline.

Stackup profile cards should be generated or curated from case-local source
evidence, such as:

- governing package or PCB stackup documents,
- material datasheets,
- user-provided Dk/Df/thickness/copper assumptions,
- Docling extraction from approved PDFs,
- engineer-reviewed stackup notes.

Do not seed active stackup cards in the shared repo just because a common
layer count or material family is expected. Case-specific stackup cards must
preserve source lineage and clearly separate measured values, user assumptions,
solver synthesis values, and missing information.
