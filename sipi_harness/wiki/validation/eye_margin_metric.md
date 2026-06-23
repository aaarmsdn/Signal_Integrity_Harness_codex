---
graph: true
id: validation_metric_eye_margin
title: Eye Margin Metric
page_type: validation_metric
domain:
  - verification
  - SI
interfaces:
  - SerDes
topics:
  - eye_diagram
  - BER
  - compliance_check
design_stage:
  - circuit_sim
  - compliance
metric_name: eye_margin
required_inputs:
  - channel Touchstone file
  - source/load model
  - data rate
  - BER target
  - mask or contour requirement
extraction_method: "Run statistical or transient channel simulation and measure eye opening using the spec-defined BER/mask method."
pass_fail_equation: "blocked_until_tier_0_spec_loaded"
output_artifacts:
  - eye_density.png
  - eye_contour.png
  - eye_margin_summary.json
source_tier: tier_0
source_ids:
  - case_tier0_source_required
outputs_to:
  - design_strategy.validation_benches
  - design_strategy.missing_spec_values
confidence: low
status: draft
concepts:
  - Eye Diagram
  - BER
  - Eye Mask
claims:
  - id: claim_001
    text: "Eye compliance requires the spec-defined BER target, source/load model, and mask or contour measurement method."
    source_id: case_tier0_source_required
    evidence_status: needs_case_citation
relationships:
  - source: BER
    predicate: defines
    target: Eye Mask
    polarity: neutral
    evidence: case_tier0_source_required
missing_information:
  - "Exact BER target, mask dimensions, contour method, and source/load model for the active interface must be extracted from tier-0 evidence."
evidence_gaps:
  - id: missing_eye_mask_requirement
    severity: blocker
    required_source_tier: tier_0
---

# Eye Margin Metric

Metric card for channel simulation eye margin and mask reporting.
