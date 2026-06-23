---
graph: true
id: validation_metric_crosstalk
title: Crosstalk Metric
page_type: validation_metric
domain:
  - verification
  - SI
interfaces:
  - SerDes
topics:
  - crosstalk
  - NEXT
  - FEXT
  - compliance_check
design_stage:
  - em_solve
  - compliance
metric_name: crosstalk
required_inputs:
  - multiport Touchstone file
  - victim lane mapping
  - aggressor lane set
  - spec-defined power-sum or voltage-transfer equation
extraction_method: "Compute NEXT/FEXT or VTF crosstalk using the victim/aggressor mapping required by the governing spec."
pass_fail_equation: "blocked_until_tier_0_spec_loaded"
output_artifacts:
  - crosstalk_vs_frequency.csv
  - crosstalk_margin_plot.png
source_tier: tier_0
source_ids:
  - case_tier0_source_required
outputs_to:
  - design_strategy.si_checks
  - design_strategy.validation_benches
  - design_strategy.missing_spec_values
confidence: low
status: draft
concepts:
  - Crosstalk
  - Aggressor
  - Victim
claims:
  - id: claim_001
    text: "Crosstalk compliance must use the aggressor set, victim definition, and equation required by the governing spec."
    source_id: case_tier0_source_required
    evidence_status: needs_case_citation
relationships:
  - source: Aggressor
    predicate: couples into
    target: Victim
    polarity: negative
    evidence: case_tier0_source_required
missing_information:
  - "Exact crosstalk equation, aggressor count, aggregation method, and threshold for the active interface are not encoded."
evidence_gaps:
  - id: missing_crosstalk_equation
    severity: blocker
    required_source_tier: tier_0
---

# Crosstalk Metric

Metric card for multi-lane victim/aggressor compliance extraction.
