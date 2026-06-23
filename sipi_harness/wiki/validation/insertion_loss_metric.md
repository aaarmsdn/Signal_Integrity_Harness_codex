---
graph: true
id: validation_metric_insertion_loss
title: Insertion Loss Metric
page_type: validation_metric
domain:
  - verification
  - SI
interfaces:
  - SerDes
topics:
  - insertion_loss
  - S_parameter
  - compliance_check
design_stage:
  - em_solve
  - compliance
metric_name: insertion_loss
required_inputs:
  - Touchstone file
  - victim port mapping
  - Nyquist frequency
  - spec-defined source/load model when VTF is required
extraction_method: "Compute victim path loss from S-parameters or voltage transfer function according to the governing spec."
pass_fail_equation: "blocked_until_tier_0_spec_loaded"
output_artifacts:
  - insertion_loss_vs_frequency.csv
  - insertion_loss_plot.png
source_tier: tier_0
source_ids:
  - case_tier0_source_required
outputs_to:
  - design_strategy.si_checks
  - design_strategy.missing_spec_values
confidence: low
status: draft
concepts:
  - Insertion Loss
  - Voltage Transfer Function
  - Nyquist Frequency
claims:
  - id: claim_001
    text: "Insertion loss compliance must use the metric, frequency point, and loading model required by the governing interface spec."
    source_id: case_tier0_source_required
    evidence_status: needs_case_citation
relationships:
  - source: Insertion Loss
    predicate: is checked at
    target: Nyquist Frequency
    polarity: neutral
    evidence: case_tier0_source_required
missing_information:
  - "Exact insertion-loss pass/fail equation, frequency points, loading model, and thresholds for the active interface are not encoded."
evidence_gaps:
  - id: missing_insertion_loss_equation
    severity: blocker
    required_source_tier: tier_0
---

# Insertion Loss Metric

Metric card for loss extraction. It intentionally blocks compliance until the
governing spec equation and loading model are cited.
