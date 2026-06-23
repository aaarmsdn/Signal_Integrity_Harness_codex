---
graph: true
id: interface_high_speed_channel
title: High-Speed Channel Interface Profile
page_type: interface_profile
domain:
  - SI
  - package
  - verification
interfaces:
  - SerDes
topics:
  - channel_routing
  - S_parameter
  - eye_diagram
  - BER
design_stage:
  - strategy
  - compliance
supported_package_classes:
  - standard_package
  - advanced_package
  - organic_package
  - substrate
design_objects:
  - lane
  - bump
  - ball
  - pad
  - via_transition
  - channel
  - package_channel
required_constraints:
  - governing_spec_version
  - package_class
  - lane_count
  - data_rate
  - channel_length
  - material_model
  - source_load_model
  - pass_fail_metrics
source_tier: tier_1
source_ids:
  - case_reviewed_source_required
outputs_to:
  - design_strategy.request_parse
  - design_strategy.routing
  - design_strategy.validation_benches
  - design_strategy.missing_spec_values
confidence: medium
status: draft
concepts:
  - High-Speed Channel
  - Interface Profile
  - Source Load Model
  - Compliance Check
claims:
  - id: claim_001
    text: "A high-speed channel request must identify the governing interface, package class, lane count, data rate, channel length, material assumptions, and required compliance metrics before final pass/fail can be assessed."
    source_id: case_reviewed_source_required
    evidence_status: engineering_policy
relationships:
  - source: Interface Profile
    predicate: selects
    target: Compliance Check
    polarity: neutral
    evidence: case_reviewed_source_required
missing_information:
  - "The active case must provide the governing interface/spec and reviewed source evidence before compliance thresholds are selected."
review:
  owner: null
  last_reviewed: null
  reviewer_status: unreviewed
---

# High-Speed Channel Interface Profile

Generic interface profile for package, PCB, connector, or interposer channels.
It defines the request fields the agent must collect before selecting
interface-specific constraints from case-local tier-0 evidence.
