# Human Checkpoints

The harness automates repeatable work, but several engineering decisions must
remain explicit.

## Source Selection

- Inspect: web research sources, user references, spec version.
- Why manual: design rules and internet sources can be wrong, outdated, or
  unrelated to the target topology.
- Decision: accept, reject, or mark as background-only.
- Harness support: source registry, access date, summary, implication fields.

## Spec Figure/Table Extraction

- Inspect: rendered PDF page, extracted rows/coordinates, figure/table ID.
- Why manual: OCR/vector extraction can reorder rows or miss graphical
  information.
- Decision: approve map/mask/table as design input or mark as proxy.
- Harness support: text JSON, page PNG, crop files, evidence-to-geometry audit.

## Stackup and Reference Planes

- Inspect: signal layers, plane layers, dielectric material, return path.
- Why manual: "maximum layer count" is not equal to available routing layers.
- Decision: approve routing layers and reference assumptions.
- Harness support: stackup YAML, geometry gate, stage report.

## Routing and Geometry

- Inspect: pad clearance, route crossings, skew, layer transitions, coupling.
- Why manual: deterministic routers still need engineering review for topology,
  manufacturability, and crosstalk risk.
- Decision: approve for EM extraction, revise, or waive as proxy.
- Harness support: manifest geometry metrics and layout images.

## HFSS Import and Ports

- Inspect: AEDT project GUI on first-time flows, layers, nets, ports, setup.
- Why manual: imports can produce empty AEDB, non-exportable ports, or lost
  stackup metadata even when scripts report success.
- Decision: approve import path and port method.
- Harness support: import summary, reopen port check, Touchstone validation.

## Solver Completion

- Inspect: solve logs, convergence, sweep range, result file.
- Why manual: solver APIs can return success while export data is unavailable
  or convergence is insufficient for compliance.
- Decision: accept as smoke/engineering/compliance or rerun with tighter setup.
- Harness support: solve summary, log checks, Touchstone metadata.

## ADS Schematic and Dataset

- Inspect: schematic connectivity, component parameters, source/load model,
  dataset and DDS.
- Why manual: ADS automation can place components correctly but still use wrong
  component filenames, unconnected nodes, or wrong spec loading.
- Decision: approve bench for metric extraction.
- Harness support: netlist/DDS/dataset paths, screenshots, metric table.

## Compliance Claim

- Inspect: all stage reports, waivers, final metrics, spec equations.
- Why manual: compliance requires traceable evidence and correct interpretation,
  not just generated files.
- Decision: pass, fail, proxy, or blocked.
- Harness support: final manifest, stage PDFs, waiver records.
