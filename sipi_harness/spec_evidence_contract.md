# Spec Evidence Contract

This harness must treat every new SI/PI task as spec-driven. Before layout,
solver setup, or compliance reporting, extract and preserve the governing
specification evidence under `outputs/<case>/spec_evidence/`.

## Required Evidence

For any requirement, map, pinout, ball map, connector pin table, escape diagram,
loading model, equation, mask, or pass/fail limit, save:

- Source document path or URL.
- Section, clause, page, figure, and table identifiers.
- Extracted text, table rows, figure rows, coordinates, equations, or limits.
- Extraction method, such as PDF text extraction, vector extraction, OCR,
  visual inspection, vendor spreadsheet import, or manual transcription.
- Figure snapshot or crop path when the source is graphical.
- Normalization assumptions, including row/column direction, origin, units,
  signal-name casing, omitted pins, and coordinate transforms.
- Reviewer status: `unreviewed`, `visual_cross_checked`, `proxy`, or
  `approved_for_design`.

For the active case, also save or reference a compliance metric coverage matrix.
This matrix is separate from individual extracted limits. It proves that the
agent looked for all requirement families in the governing source before
choosing benches.

Required coverage families:

- Frequency-domain S-parameter, transfer-function, impedance, or TDR metrics.
- Crosstalk, noise coupling, or aggressor aggregation metrics.
- Skew, timing, jitter, or phase/timing budget metrics.
- Transient waveform, eye diagram, eye mask, bathtub, BER contour, or statistical
  channel metrics.
- Source, receiver, termination, loading, package, connector, and fixture
  models needed by any metric.
- Power, rail, PDN, droop, ripple, or SSN metrics when the request or spec
  includes power integrity.
- Required report, plot, dataset, or evidence artifacts.

Every row must state `implemented`, `proxy_only`, `not_applicable`, or
`blocked_missing_evidence`, and must include source identifiers when the row is
driven by the governing spec.

## Evidence Bundle Files

For a general PDF specification, start with:

```powershell
npm run extract:spec-evidence -- --pdf <spec.pdf> --case-dir <outputs/case> --request-file <request.txt>
```

This creates a case-local `spec_evidence/` bundle:

- `spec_manifest.json`: source PDF path, SHA256, page count, and review policy.
- `spec_inventory.json`: table of contents, processed pages, page scores, page
  text/block/render artifact paths.
- `spec_candidates.json`: unreviewed candidate clauses, numeric limits, tables,
  figures, equations, masks, loading models, maps, and pin/ball/bump-map hits.
- `compliance_metric_coverage.json` or a strategy-embedded equivalent:
  discovered requirement families, source IDs, implementation status, bench
  mapping, and blockers.
- `spec_review_queue.json`: engineer review queue. Items are not allowed to
  drive layout or compliance until classified and reviewed.
- `pages/*.txt`: raw page text.
- `pages/*_blocks.json`: text/image block positions and text spans.
- `renders/*.png`: rendered page images for candidate or all pages, depending
  on extraction mode.

The older `extract:pdf-evidence` page tool remains useful for focused extraction
after the inventory identifies the page/table/figure to inspect.

## Separation From Wiki

The LLM wiki stores reusable design knowledge. It must not be the sole source
of governing values. A spec evidence bundle stores case-local tier-0 evidence.

```text
Spec PDF -> spec_evidence/* -> reviewed constraints/maps/equations
Wiki cards + reviewed spec_evidence -> strategy/design_strategy.yaml
```

If `spec_candidates.json` contains a possible numeric limit, that value is only
a candidate. It becomes a usable `spec_constraint` only after a reviewed record
links it to source PDF, page, table/figure/equation/clause, extraction method,
normalization assumptions, and reviewer status.

## Figure-Derived Maps

If a ball map, pin map, connector pinout, escape diagram, eye mask, or loading
network exists only as a PDF figure, do not route or claim compliance from memory.
Read the surrounding text and caption, extract the figure content, and cross-check
against a rendered page or cropped figure. Store the crop/screenshot path in the
evidence bundle when possible.

If the figure cannot be reliably extracted or visually checked, mark the evidence
as `proxy` and state that the result is not a final compliance result.

## Design Gate

The design stage may begin only after the active case strategy references the
evidence bundle. Compliance may be claimed only when every figure/table-derived
map used for connectivity has reviewer status `visual_cross_checked` or
`approved_for_design`.

For final compliance thresholds, require `approved_for_design`. For geometry
derived from figures or tables, require at least `visual_cross_checked`.

For final compliance benches, require complete metric coverage. If the
governing source defines an eye diagram, eye mask, BER contour, bathtub, jitter,
or other transient/statistical metric, the strategy and bench report must
implement that metric or explicitly block compliance. A frequency-domain
S-parameter fallback report is only a sanity/proxy artifact unless the governing
source itself defines it as sufficient.

The evidence bundle must be tied to generated geometry. For every
figure/table-derived signal, pin, ball, connector contact, or package landing
used as a net endpoint or port, save an evidence-to-geometry audit row with:

- Source identifier, such as figure row/column, table row, pin name, or ball
  coordinate.
- Generated coordinate, layer, net name, and port intent.
- Any reordering, mirroring, rotation, or escape-order transform.
- Whether the coordinate is exact from the source, derived by a documented
  transform, or a proxy/synthetic placement.

If the generated layout stores evidence but does not drive coordinates from it,
the layout is a proxy and must not be reported as spec-compliant.
