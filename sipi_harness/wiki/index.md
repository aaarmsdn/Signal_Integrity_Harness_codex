---
graph: false
kind: wiki_control
---

# Index

Content catalog for the SI/PI LLM wiki. Read this first when selecting pages for a design strategy.

- Graph pages: 8
- Hub pages: 12
- Control pages: 13

## Hub Pages

- [[Constraints]] - overview hub
- [[Design Rules]] - overview hub
- [[KiCad Design Rules]] - overview hub
- [[LLM Wiki Architecture]] - overview hub
- [[Package and PCB Strategy]] - overview hub
- [[Power Integrity and PDN]] - overview hub
- [[Project Cases]] - overview hub
- [[Signal Integrity]] - overview hub
- [[Source Cards]] - overview hub
- [[Spec to Design Strategy]] - overview hub
- [[Stackup Profiles]] - overview hub
- [[Verification Strategy]] - overview hub

## interface profile

- [[High-Speed Channel Interface Profile]] - --- _(topics: channel_routing, S_parameter, eye_diagram, BER; stage: strategy, compliance; tier: tier_1)_

## validation flow

- [[Channel Validation Flow]] - --- _(topics: HFSS_3D_Layout, Touchstone, ADS, compliance_check; stage: extraction, em_solve, circuit_sim, compliance; tier: tier_1)_

## validation metric

- [[Crosstalk Metric]] - --- _(topics: crosstalk, NEXT, FEXT, compliance_check; stage: em_solve, compliance; tier: tier_0)_
- [[Eye Margin Metric]] - --- _(topics: eye_diagram, BER, compliance_check; stage: circuit_sim, compliance; tier: tier_0)_
- [[Insertion Loss Metric]] - --- _(topics: insertion_loss, S_parameter, compliance_check; stage: em_solve, compliance; tier: tier_0)_
- [[Return Loss Metric]] - --- _(topics: return_loss, S_parameter, TDR; stage: em_solve, compliance; tier: tier_1)_
- [[S-Parameter Sanity Check]] - --- _(topics: S_parameter, Touchstone, compliance_check; stage: em_solve, compliance; tier: tier_1)_
- [[Skew Metric]] - --- _(topics: skew, jitter; stage: layout, compliance; tier: tier_1)_
