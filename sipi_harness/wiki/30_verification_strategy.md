---
graph: false
kind: hub_page
id: wiki_verification_strategy
topic: verification_strategy
summary: "Spec-driven verification links design requirements to EM extraction, Touchstone sanity checks, circuit simulation, and report evidence."
concepts:
  - Verification Strategy
  - Verification Method
  - EM Extraction
  - HFSS 3D Layout
  - Touchstone
  - ADS
  - Nyquist Frequency
  - Frequency Sweep
  - Eye Mask
  - Report Evidence
claims:
  - "Simulation setup should be derived from the spec measurement method and the design strategy, not from a remembered example."
  - "For channel checks, frequency coverage should normally extend to at least three times the Nyquist frequency unless the spec defines a stricter band."
  - "Frequency spacing should be dense enough to capture resonances, crosstalk nulls, and package/PCB launch features; sparse sweeps are smoke tests only."
  - "Touchstone sanity checks must verify port count, port order, reference impedance, units, and stop frequency before ADS or compliance analysis."
relationships:
  - "Verification Strategy|uses|EM Extraction"
  - "EM Extraction|generates|Touchstone"
  - "Touchstone|feeds|ADS"
  - "Nyquist Frequency|sets|Frequency Sweep"
  - "ADS|checks|Eye Mask"
  - "Verification Method|produces|Report Evidence"
---

# Verification Strategy

Verification strategy turns a design target into reproducible evidence. It
starts before layout: define what must be measured, how the source and load are
modeled, what simulator produces the result, and which equation or mask decides
pass/fail.

## Frequency Coverage

For digital channels, use the active data rate to compute Nyquist frequency:

```text
fN = data_rate / 2
```

As a default SI/PI harness rule, EM extraction and Touchstone export should
cover at least `5 * fN`. This is not final signoff by itself; it is a minimum
coverage rule so ADS/circuit checks can see package/PCB resonances and
crosstalk behavior beyond the fundamental Nyquist point.

Sweep density depends on the job:

- Smoke test: 10-30 points, only for tool/path validation.
- Engineering check: 101-401 points from DC/low frequency to at least `5*fN`.
- Resonant package/PDN/connector structures: adaptive or segmented sweeps with
  finer spacing around expected resonances, nulls, anti-resonances, or mask
  boundaries.

## Evidence Checks

Before using solver output, verify:

- port count and port order
- reference impedance
- frequency unit and stop frequency
- passive/causal warnings where available
- whether the setup is a smoke test, engineering estimate, or spec-defined
  compliance bench

## Typed Cards

- [[S-Parameter Sanity Check]]
- [[Insertion Loss Metric]]
- [[Return Loss Metric]]
- [[Crosstalk Metric]]
- [[Skew Metric]]
- [[Eye Margin Metric]]
- interface-specific validation flow selected by the active request
