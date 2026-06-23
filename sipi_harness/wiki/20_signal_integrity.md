---
graph: false
kind: hub_page
id: wiki_signal_integrity
topic: signal_integrity
summary: "Signal integrity strategy organizes impedance, insertion loss, return loss, crosstalk, return path, jitter, and eye closure into connected design decisions."
concepts:
  - Signal Integrity
  - Impedance
  - Insertion Loss
  - Return Loss
  - Reflection
  - Crosstalk
  - Return Path
  - Via Transition
  - Eye Diagram
  - Jitter
  - Length Matching
claims:
  - "Controlled impedance reduces reflections but does not by itself guarantee eye opening."
  - "Insertion loss, return loss, crosstalk, jitter, and receiver loading must be checked under the spec-defined source/load model."
  - "Return path discontinuities at vias, plane splits, and reference changes can create reflection, mode conversion, crosstalk, and EMI risk."
  - "Length matching should be evaluated as delay skew in UI or ps, not just as nominal routed distance."
relationships:
  - "Signal Integrity|contains|Impedance"
  - "Signal Integrity|contains|Insertion Loss"
  - "Signal Integrity|contains|Return Loss"
  - "Signal Integrity|contains|Crosstalk"
  - "Signal Integrity|contains|Return Path"
  - "Impedance|controls|Reflection"
  - "Reflection|is measured by|Return Loss"
  - "Insertion Loss|closes|Eye Diagram"
  - "Crosstalk|closes|Eye Diagram"
  - "Jitter|closes|Eye Diagram"
  - "Via Transition|disrupts|Return Path"
  - "Length Matching|controls|Jitter"
---

# Signal Integrity

Signal integrity is the design of interconnects so the receiver sees the
intended waveform under the required source, load, data-rate, and noise
conditions.

## Category Map

```text
Signal Integrity
  -> Impedance
     -> Reflection
     -> Return Loss
  -> Insertion Loss
     -> Eye Diagram
  -> Crosstalk
     -> Eye Diagram
  -> Return Path
     -> Via Transition
  -> Timing
     -> Length Matching
     -> Jitter
```

## Strategy Checklist

1. Define source/load model, signaling mode, data rate, edge rate, and receiver
   threshold/mask.
2. Select stackup and geometry for target impedance.
3. Keep return paths continuous through vias, layers, packages, connectors, and
   plane transitions.
4. Control insertion loss and return loss across the spec frequency band.
5. Classify victim/aggressor lanes and compute crosstalk using the spec method.
6. Convert length mismatch into delay skew and UI fraction.
7. Verify the eye or mask with the exact BER/statistical method required by the
   spec.

## Typed Cards

- [[Insertion Loss Metric]]
- [[Return Loss Metric]]
- [[Crosstalk Metric]]
- [[Skew Metric]]
- [[Eye Margin Metric]]

Case-specific design-rule cards, such as impedance control, reference-plane
continuity, and via-transition rules, should be generated under
`design_rules/` from raw sources or reviewed references before they are linked
from this hub.
