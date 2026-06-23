---
graph: true
id: validation_metric_sparameter_sanity_check
title: S-Parameter Sanity Check
page_type: validation_metric
domain:
  - verification
  - SI
topics:
  - S_parameter
  - Touchstone
  - compliance_check
design_stage:
  - em_solve
  - compliance
metric_name: sparameter_sanity_check
required_inputs:
  - Touchstone file
  - port map
  - frequency vector
extraction_method: "Parse Touchstone, verify port count/order, passive-looking trends, DC/low-frequency continuity, and expected victim/aggressor connectivity."
pass_fail_equation: "Engineering sanity gate; formal compliance requires interface-specific tier_0 equations."
output_artifacts:
  - parsed_sparameter_summary.json
  - sparameter_sanity_report.pdf
source_tier: tier_1
source_ids:
  - case_reviewed_source_required
outputs_to:
  - design_strategy.si_checks
  - design_strategy.validation_benches
confidence: medium
status: draft
concepts:
  - S-Parameter
  - Touchstone
  - Port Map
claims:
  - id: claim_001
    text: "A Touchstone file must be checked for port count, ordering, and basic frequency coverage before circuit compliance simulation."
    source_id: case_reviewed_source_required
    evidence_status: engineering_policy
relationships:
  - source: Touchstone
    predicate: requires
    target: Port Map
    polarity: neutral
    evidence: case_reviewed_source_required
missing_information: []
---

# S-Parameter Sanity Check

Pre-compliance validation metric for extracted S-parameter files.
