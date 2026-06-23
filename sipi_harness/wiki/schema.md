---
graph: false
kind: wiki_control
schema_version: "2.0"
---

# SIPI Wiki Schema v2

The wiki is a machine-readable SIPI design knowledge layer. Human overview
pages are hubs. Agent retrieval should prefer small typed cards in
`sources/`, `interfaces/`, `constraints/`, `design_rules/`, `stackups/`,
`validation/`, and `cases/`.

## Supported Page Types

```yaml
page_types:
  - source_card
  - interface_profile
  - spec_constraint
  - design_rule
  - stackup_profile
  - validation_metric
  - validation_flow
  - project_case
```

## Required Frontmatter

Every `graph: true` card must include:

```yaml
required_frontmatter:
  - graph
  - id
  - title
  - page_type
  - domain
  - topics
  - design_stage
  - source_tier
  - source_ids
  - confidence
  - status
```

Recommended shape:

```yaml
---
graph: true
id: design_rule_case_specific_example
title: Case-Specific Design Rule Example
page_type: design_rule
domain:
  - SI
  - package
interfaces:
  - SerDes
spec_versions:
  - active_case
applicability:
  package_type:
    - organic_package
  layer_count:
    - 4L
  data_rate:
    min_gbps: null
    max_gbps: null
  lane_count:
    - active_case
  channel_length_mm:
    min: null
    max: null
topics:
  - channel_routing
  - via_transition
  - return_loss
  - return_path
design_stage:
  - strategy
  - layout
  - em_solve
claim_type: heuristic
evidence_level: source_grounded
source_tier: tier_1
source_ids:
  - source_id_or_path
outputs_to:
  - design_strategy.routing
  - design_strategy.si_checks
confidence: medium
status: draft
concepts:
  - Via Transition
  - Return Loss
  - Return Path
claims:
  - id: claim_001
    text: "Short source-grounded claim."
    source_id: source_id_or_path
    evidence_status: cited
    applies_when:
      - high_speed_package_channel
relationships:
  - source: Via Transition
    predicate: affects
    target: Return Loss
    polarity: negative
    evidence: source_id_or_path
missing_information:
  - "Exact interface-specific numeric limit must be read from the governing spec."
review:
  owner: null
  last_reviewed: null
  reviewer_status: unreviewed
---
```

Structured `relationships` are preferred. The legacy string format
`Concept A|predicate|Concept B` is temporarily supported, but `npm run
lint:wiki` warns on it.

## Source Tier Policy

```yaml
source_tier:
  tier_0:
    description: official spec, user-provided governing spec, internal approved requirement
    allowed_for:
      - compliance_limit
      - pass_fail_threshold
      - spec_constraint
  tier_1:
    description: vendor app note, EDA vendor article, official design guide
    allowed_for:
      - design_rule
      - validation_flow
      - engineering_rationale
  tier_2:
    description: paper, tutorial, public presentation
    allowed_for:
      - background
      - candidate_strategy
      - cross_check
  tier_3:
    description: blog, forum, uncited web content
    allowed_for:
      - search_seed
      - context_only
```

Rules:

- A `spec_constraint` page must have at least one `tier_0` source.
- Numeric compliance limits must not appear without a `source_id`.
- Numeric pass/fail thresholds must not appear without a `tier_0` source.
- `tier_3` sources must never be promoted into final compliance constraints.
- Design rules may use `tier_1` or better, but must mark whether claims are
  heuristic, source-grounded, proxy-only, or missing.

## Page-Type Requirements

```yaml
page_type_specific:
  spec_constraint:
    required:
      - interfaces
      - spec_versions
      - constraints
      - source_ids
    forbidden_without_tier_0:
      - numeric_limit
      - pass_fail_threshold
  validation_metric:
    required:
      - metric_name
      - required_inputs
      - extraction_method
      - pass_fail_equation
      - output_artifacts
  design_rule:
    required:
      - applicability
      - design_knobs
      - validation_checklist
  stackup_profile:
    required:
      - material
      - layer_count
      - geometry_parameters
      - assumptions
  source_card:
    required:
      - source_type
      - source_tier
      - version
      - access
      - allowed_usage
  interface_profile:
    required:
      - interfaces
      - supported_package_classes
      - design_objects
      - required_constraints
  validation_flow:
    required:
      - required_inputs
      - steps
      - output_artifacts
      - pass_fail_gates
  project_case:
    required:
      - problem
      - final_strategy
      - reusable_rules
      - evidence_artifacts
```

## Strategy Output Contract

Cards must declare `outputs_to` so retrieval can build
`strategy/design_strategy.yaml` with evidence lineage:

```yaml
outputs_to:
  - design_strategy.routing
  - design_strategy.stackup
  - design_strategy.si_checks
  - design_strategy.pi_checks
  - design_strategy.validation_benches
  - design_strategy.missing_spec_values
```

The strategy generator must distinguish:

- source-backed constraint
- engineering heuristic
- proxy-only estimate
- missing or blocking spec value

`design_strategy.validation_benches` is not just a list of wiki pages. It must
be a machine-readable bench contract:

```yaml
validation_benches:
  evidence_pages:
    - validation_flow_or_metric_card
  spec_requirements:
    schema_version: spec_bench_requirements_v1
    status: requirements_extracted_from_tier0_candidates
    metric_requirements:
      - id: spec_req_eye_mask
        metric_name: eye_mask
        domain: statistical_transient
        default_bench: eye_mask_check
        required_inputs:
          - channel model
          - source/load model
          - data rate
          - mask geometry
        source_tier: tier_0
        evidence_ids:
          - candidate_or_reviewed_evidence_id
        pass_fail_equation: extract_from_evidence_candidates
        status: source_candidates_found
        review_status: requires_review
    coverage_matrix:
      - metric_name: eye_mask
        status: source_candidates_found
        default_bench: eye_mask_check
        evidence_count: 1
  required_benches:
    - spec-derived metric requirement objects
  generic_implementation_benches:
    - built-in generic benches that can implement source-backed requirements
      without an interface-specific adapter
  blocked_benches:
    - source-backed requirements that need an adapter or engineer-selected
      bench topology before compliance can proceed
      adapter_synthesis:
        status: adapter_generation_possible_from_requirement_contract
        contract_id: adapter_contract_eye_mask
        inputs:
          - source/load model
          - data rate
          - mask geometry
        expected_outputs:
          - machine-readable metric JSON
          - plot images when applicable
          - stage report section with source evidence IDs
        recommended_flow:
          tool_family: ADS_ChannelSim_or_equivalent
          bench_type: statistical_or_transient_eye
  implementation_benches:
    - optional benches implemented by the selected tool adapter
  spec_profile:
    profile: optional_interface_or_standard_adapter
    status: implementation_adapter_available_for_extracted_requirements
```

The generic generator must extract required bench families from tier-0 spec
evidence first. Interface-specific adapters, such as an ADS profile for a
particular standard, may only attach implementation commands after the generic
requirements exist. Do not let an adapter replace the source-derived
`required_benches`.

If no interface-specific adapter exists, the strategy is still valid. Built-in
generic benches may implement source-backed requirements such as characteristic
impedance, insertion loss, return loss, crosstalk, and delay/skew when the
required artifacts exist. Requirements that need a specific circuit topology,
loading model, statistical eye setup, BER contour, or mask implementation must
be listed in `blocked_benches` rather than silently replaced by proxy data.
Each blocked bench should include an `adapter_synthesis` contract so a case-local
adapter can be created on demand. A generated adapter may unblock the metric
only when it uses the extracted requirement evidence and writes traceable
machine-readable outputs.

## Fusion Input Shape

Case-level knowledge fusion input should use this structure:

```yaml
request_parse:
  interface: active_case
  spec_version: active_case
  lane_count: active_case
  data_rate_gbps: active_case
  package:
    type: organic_package
    layer_count: 4
    dk: 4.3
    df: 0.01
  channel_length_mm: active_case
retrieved_pages:
  spec_constraints:
    - generated_spec_constraint_from_case_sources
    - generated_loss_constraint_from_case_sources
  design_rules:
    - generated_design_rule_from_case_sources
  stackups:
    - generated_stackup_profile_from_case_sources
  validation:
    - insertion_loss_metric
evidence_gaps:
  - id: missing_exact_channel_loss_budget
    severity: blocker
    required_source_tier: tier_0
strategy_output_map:
  routing:
    from:
      - generated_design_rule_from_case_sources
  compliance:
    from:
      - generated_compliance_bench_constraint
spec_bench_requirements:
  metric_requirements:
    - metric_name: characteristic_impedance
      domain: frequency_or_tdr
    - metric_name: insertion_loss
      domain: frequency
    - metric_name: crosstalk
      domain: frequency
    - metric_name: voltage_transfer_function
      domain: frequency
    - metric_name: eye_mask
      domain: statistical_transient
    - metric_name: ber_contour
      domain: statistical_transient
  implementation_adapter:
    profile: optional
    status: optional_adapter_must_not_override_required_benches
```

Run `npm run wiki:ops`, `npm run lint:wiki`, and `npm run build:graph` after
editing graph cards.
