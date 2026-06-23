---
graph: true
id: validation_metric_skew
title: Skew Metric
page_type: validation_metric
domain:
  - verification
  - SI
topics:
  - skew
  - jitter
design_stage:
  - layout
  - compliance
metric_name: skew
required_inputs:
  - routed length per lane
  - stackup velocity estimate or extracted delay
  - data rate
extraction_method: "Convert length or extracted delay into lane-to-lane delta in ps and UI."
pass_fail_equation: "Use tier_0 interface skew limit when available; otherwise report as planning margin."
output_artifacts:
  - routed_delay_table.csv
  - skew_summary.json
source_tier: tier_1
source_ids:
  - case_reviewed_source_required
outputs_to:
  - design_strategy.si_checks
  - design_strategy.routing
confidence: medium
status: draft
concepts:
  - Skew
  - Delay
  - UI
claims:
  - id: claim_001
    text: "Skew reporting should include both absolute delay difference and unit-interval fraction."
    source_id: case_reviewed_source_required
    evidence_status: engineering_policy
relationships:
  - source: Delay
    predicate: converts to
    target: UI
    polarity: neutral
    evidence: case_reviewed_source_required
missing_information:
  - "Exact interface skew limit requires tier_0 evidence."
---

# Skew Metric

Metric card for routed and extracted delay matching.
