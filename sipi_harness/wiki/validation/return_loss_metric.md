---
graph: true
id: validation_metric_return_loss
title: Return Loss Metric
page_type: validation_metric
domain:
  - verification
  - SI
topics:
  - return_loss
  - S_parameter
  - TDR
design_stage:
  - em_solve
  - compliance
metric_name: return_loss
required_inputs:
  - Touchstone file
  - port mapping
  - frequency band
extraction_method: "Evaluate reflection terms for each driven port and inspect launch/transition discontinuities."
pass_fail_equation: "Use interface-specific threshold when defined; otherwise report as engineering diagnostic."
output_artifacts:
  - return_loss_vs_frequency.csv
  - return_loss_plot.png
source_tier: tier_1
source_ids:
  - case_reviewed_source_required
outputs_to:
  - design_strategy.si_checks
confidence: medium
status: draft
concepts:
  - Return Loss
  - Reflection
  - Launch
claims:
  - id: claim_001
    text: "Return loss is a launch and impedance-continuity diagnostic even when the governing spec does not make it a final compliance gate."
    source_id: case_reviewed_source_required
    evidence_status: engineering_policy
relationships:
  - source: Reflection
    predicate: is measured by
    target: Return Loss
    polarity: neutral
    evidence: case_reviewed_source_required
missing_information:
  - "Interface-specific return-loss threshold is not assumed."
---

# Return Loss Metric

Metric card for reflection diagnostics.
