---
graph: false
kind: hub_page
id: wiki_spec_to_design_strategy
topic: spec_to_design
summary: "Spec-to-design strategy converts clauses, tables, figures, masks, and loading models into traceable design requirements and verification benches."
concepts:
  - Specification
  - Requirement
  - Design Strategy
  - Ball Map
  - Pin Map
  - Loading Model
  - Eye Mask
  - Evidence
  - Geometry Gate
  - Verification Method
claims:
  - "A PDF figure-derived map must be extracted and visually checked before it drives coordinates."
  - "Each requirement should link to design knobs and verification methods."
  - "A design strategy is incomplete until it defines source/load assumptions, pass/fail equations, and report artifacts."
relationships:
  - "Specification|contains|Requirement"
  - "Specification|contains|Ball Map"
  - "Specification|contains|Pin Map"
  - "Specification|defines|Loading Model"
  - "Specification|defines|Eye Mask"
  - "Requirement|drives|Design Strategy"
  - "Evidence|supports|Requirement"
  - "Design Strategy|defines|Geometry Gate"
  - "Design Strategy|defines|Verification Method"
---

# Spec to Design Strategy

Specification-driven design starts by turning source clauses and figures into
traceable requirements. The goal is not to remember what a standard usually
says; the goal is to preserve the page/table/figure evidence that drives the
current design.

## Strategy Objects

- Requirement: parameter, limit, condition, mode, speed, and scope.
- Map: ball map, pin map, connector pinout, escape order, or lane assignment.
- Loading model: source resistance, capacitance, termination, package, and
  measurement node definitions.
- Mask/equation: exact pass/fail method, units, and target BER/frequency.
- Geometry gate: pad/via/trace clearance, routing topology, length/delay skew,
  reference continuity, and port availability.
- Verification method: EM setup, circuit bench, dataset, DDS/plot, and report.

## Required Traceability

Each generated coordinate, net, port, or verification bench should link back to
the source requirement or figure/table row that caused it. If this link is
missing, the result is a proxy and must not be reported as compliance.

## Typed Cards

Retrieve typed cards by the active request, not by a default interface. A
strategy generator should first match the request parse against:

- interface profiles for the requested protocol or standard
- spec constraints from reviewed tier-0 evidence
- stackup profiles matching package/board material and layer count
- design rules matching routing topology, impedance, loss, crosstalk, skew,
  PDN, or thermal concerns
- validation metrics and flows matching the required frequency-domain and
  transient-domain benchmarks

Interface-specific card sets may be generated or loaded for an active case, but
they must not be treated as default strategy inputs unless the request and
tier-0 evidence select that interface.
