---
name: pdf-spec-evidence
description: Extract and preserve tier-0 evidence from PDF specifications before SI/PI package, PCB, channel, or compliance work. Use when a task depends on a governing spec PDF, table, figure, equation, pin/ball/bump map, eye mask, loading diagram, numeric limit, or page image; create a case-local spec_evidence bundle and block design/compliance claims until evidence is reviewed.
---

# PDF Spec Evidence

Use this skill before layout, routing, EM setup, ADS benches, or compliance
reports whenever governing information comes from a PDF spec.

## Required Separation

Keep this layer separate from the LLM wiki:

```text
Spec PDF -> outputs/<case>/spec_evidence/* -> reviewed tier-0 evidence
Wiki cards + reviewed spec evidence -> strategy/design_strategy.yaml
```

The wiki provides reusable design knowledge. The `spec_evidence/` bundle
provides case-local governing values, maps, equations, masks, and loading
models. Do not promote a candidate number from the PDF into a compliance limit
until it is reviewed and tied to page/table/figure/equation evidence.

## Dependency Gate

Run this in the harness Python environment before relying on rendered figures:

```powershell
cd <repo>\sipi_harness
npm run setup:pdf-python
```

For a non-mutating check:

```powershell
npm run check:pdf-python
```

PyMuPDF (`fitz`) is required for full rendered page PNGs. If rendering is not
available, mark graphical evidence review as degraded and do not claim final
compliance from figure-derived geometry.

## Whole-Document Extraction

Start with the full-document inventory:

```powershell
npm run extract:spec-evidence -- --pdf <path-to-spec.pdf> --case-dir <outputs/case> --request-file <request.txt>
```

Useful options:

```powershell
--keyword "bump map" --keyword "voltage transfer function"
--max-pages 50
--render candidates
--render all
```

Expected bundle:

- `spec_evidence/spec_manifest.json`: PDF path, SHA256, page count, review policy.
- `spec_evidence/spec_inventory.json`: TOC, ranked pages, page text/block/render artifact paths.
- `spec_evidence/spec_candidates.json`: unreviewed candidate clauses, numeric limits, tables, figures, equations, masks, loading models, and maps.
- `spec_evidence/compliance_metric_coverage.json` or equivalent strategy section:
  matrix of every discovered requirement family and whether it is implemented,
  proxy-only, not applicable, or blocked.
- `spec_evidence/spec_review_queue.json`: review queue before evidence can drive design or compliance.
- `spec_evidence/pages/*.txt`: raw page text.
- `spec_evidence/pages/*_blocks.json`: text/image blocks and span coordinates.
- `spec_evidence/renders/*.png`: rendered candidate pages or all pages.

## Focused Page Extraction

After inventory identifies a page/table/figure, run focused extraction:

```powershell
npm run extract:pdf-evidence -- --pdf <path-to-spec.pdf> --page 10 --out-dir <outputs/case>\spec_evidence --tag spec_page10 --section "clause" --figure "Figure X-Y"
```

Expected focused outputs:

- `*_text.txt`
- `*_text_positions.json`
- `*_text_positions.png`
- `*_render.png`
- `*_image_N.*`
- `*_evidence_summary.json`

## Design Gate

Before geometry generation:

1. Confirm the case has `spec_evidence/spec_manifest.json`.
2. Check `spec_candidates.json` for relevant tables, figures, equations, maps,
   loading models, and numeric limits.
3. Build a compliance metric coverage matrix from the whole spec inventory,
   not only from remembered keywords or the user's prompt. The matrix must scan
   for at least: S-parameter or transfer-function limits, impedance/TDR,
   crosstalk, skew/timing, jitter, transient waveform/eye/mask, BER/bathtub or
   contour requirements, loading/source/receiver models, power/rail/PDN
   limits, and required report artifacts. Each row must state one of
   `implemented`, `proxy_only`, `not_applicable`, or `blocked_missing_evidence`.
4. Classify candidates into spec constraints, maps, masks, loading models,
   equations, or ignored items.
5. For every discovered metric family, record the page/table/figure/equation
   evidence ID and map it to a planned validation bench or an explicit blocker.
   If the spec contains an eye diagram, eye mask, BER contour, bathtub, or
   jitter requirement, the strategy must include the corresponding transient or
   statistical bench; do not replace it with an S-parameter-only fallback.
6. For figure/table-derived coordinates or connectivity, require
   `visual_cross_checked` or `approved_for_design`.
7. For compliance thresholds, require `approved_for_design`.
8. Reference reviewed evidence IDs from `strategy/design_strategy.yaml`,
   geometry manifests, route records, port intents, ADS benches, and reports.

If evidence is missing or unreviewed, proceed only as an explicitly marked
proxy and keep compliance status blocked.
