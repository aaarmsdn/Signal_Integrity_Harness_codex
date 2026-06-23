---
graph: true
id: validation_flow_channel
title: Channel Validation Flow
page_type: validation_flow
domain:
  - verification
  - SI
  - package
interfaces:
  - SerDes
topics:
  - HFSS_3D_Layout
  - Touchstone
  - ADS
  - compliance_check
design_stage:
  - extraction
  - em_solve
  - circuit_sim
  - compliance
required_inputs:
  - PCB or package layout
  - port intent map
  - stackup/material model
  - governing tier-0 constraints
  - validation metric cards
steps:
  - "Generate geometry and port intent from layout source."
  - "Import to field solver and create ports from explicit intent."
  - "Solve the spec-required band; use proxy coverage only when marked as non-compliance."
  - "Export Touchstone with verified port order."
  - "Run benchmark checks for required frequency-domain and transient-domain metrics."
  - "Generate stage reports with plots, source lineage, and pass/block status."
output_artifacts:
  - design_strategy.yaml
  - layout_manifest.json
  - hfss_touchstone.sNp
  - benchmark_dataset
  - stage_reports
pass_fail_gates:
  - "BLOCKED if tier-0 numeric limits or bench requirements are absent."
  - "BLOCKED if port order cannot be verified."
  - "PASS only when every tier-0 metric has a source-backed threshold and computed margin."
source_tier: tier_1
source_ids:
  - case_reviewed_source_required
  - case_tier0_source_required
outputs_to:
  - design_strategy.validation_benches
  - design_strategy.missing_spec_values
confidence: medium
status: draft
concepts:
  - HFSS 3D Layout
  - Touchstone
  - ADS
  - Compliance Check
claims:
  - id: claim_001
    text: "A channel validation flow must preserve port intent, port order, source lineage, and stage evidence from layout through circuit simulation."
    source_id: case_reviewed_source_required
    evidence_status: engineering_policy
relationships:
  - source: HFSS 3D Layout
    predicate: exports
    target: Touchstone
    polarity: neutral
    evidence: case_reviewed_source_required
  - source: Touchstone
    predicate: feeds
    target: ADS
    polarity: neutral
    evidence: case_reviewed_source_required
missing_information:
  - "Exact compliance bench parameters must be loaded from the active governing source before final pass/fail."
---

# Channel Validation Flow

Generic validation flow linking layout, EM extraction, Touchstone sanity,
benchmark simulation, and report gates.
