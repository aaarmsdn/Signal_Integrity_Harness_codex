---
graph: false
kind: wiki_control
---

# Overview

Auto-generated summary of the current SI/PI LLM wiki structure.

## Counts

- Wiki graph pages: 8
- Graph concepts: 804
- Graph documents: 107
- Graph links: 1532

## Topics

- ADS: 1
- BER: 2
- FEXT: 1
- HFSS_3D_Layout: 1
- NEXT: 1
- S_parameter: 4
- TDR: 1
- Touchstone: 2
- channel_routing: 1
- compliance_check: 5
- crosstalk: 1
- eye_diagram: 2
- insertion_loss: 1
- jitter: 1
- return_loss: 1
- skew: 1

## Page Types

- interface_profile: 1
- validation_flow: 1
- validation_metric: 6

## Design Stages

- circuit_sim: 2
- compliance: 8
- em_solve: 5
- extraction: 1
- layout: 1
- strategy: 1

## Communities

- community_llm_wiki: Knowledge is stored as source-linked graph primitives, then retrieved by local entity search or broader community summaries.
- community_pdn: PDN work centers on target impedance, VRM behavior, stackup, decoupling placement, IR drop, and transient response.
- community_si_coupling: SI behavior is coupled to power delivery through return path discontinuities, simultaneous switching noise, and plane resonances.
- community_toolchain: KiCAD, PyAEDT, and ADS become evidence-producing tools connected to the same wiki graph.
- community_return_path_strategy: High-speed routing must preserve signal-return proximity through planes, vias, splits, and package escape regions.
- community_pdn_strategy: PDN design balances target impedance, resonance damping, decap placement, loop inductance, model quality, VRM behavior, IR drop, and transient response.
- community_si_noise_strategy: Crosstalk, SSN, ground bounce, via discontinuity, and return loss are managed through geometry, topology, timing, and extraction-based checks.
- community_vendor_app_notes: Vendor application notes translate device and measurement experience into practical layout, PDN, debug, and compliance checks.
- community_measurement_debug: Lab validation connects eye diagrams, jitter, TDR/VNA, rail ripple, BER, and S-parameter quality back to graph requirements and design rules.
- community_si_formulas: Core signal-integrity equations for reflection, return/insertion loss, bandwidth, delay, impedance, wavelength, and loss sanity checks.
- community_pi_formulas: Core power-integrity equations for target impedance, capacitor impedance, SRF, IR drop, resistive loss, inductive bounce, and decoupling loop noise.
- community_tool_connectors: MCP and skill connectors that turn wiki/spec knowledge into design, simulation, and analysis actions.
- Knowledge Intake: Web research and user-provided references collected before design strategy generation.
- Docling Evidence: Layout-aware source chunks converted by Docling and awaiting review/promotion.
- Raw Sources: Local ignored source inventory staged for evidence extraction, Docling conversion, and typed-card promotion.
- Signal Integrity: Loss, impedance, reflection, return path, crosstalk, timing, and frequency/transient-domain design strategies.
- Power Integrity: PDN impedance, IR drop, decoupling, SSN, rail noise, and transient response strategies.
- Package and PCB: Stackup, launch, via, pad, escape routing, length matching, and geometry gates.
- Verification Strategy: EM extraction, Nyquist coverage, Touchstone, ADS checks, masks, and report evidence.

## Graph Health Highlights

- Isolated concepts: 40
- Bridge concepts: 20
- Sparse communities: 12

Run `npm run lint:wiki` for a detailed health report.
