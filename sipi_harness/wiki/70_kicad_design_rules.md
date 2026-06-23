---
graph: false
kind: hub_page
id: wiki_kicad_design_rules
topic: pcb_design_rules
summary: "PCB design-rule strategy maps electrical requirements to stackup, nets, constraints, DRC, port metadata, and solver-ready geometry."
concepts:
  - PCB Design Rule
  - KiCad
  - DRC
  - Stackup
  - Net Class
  - Differential Pair
  - Controlled Impedance
  - Port Intent
  - Geometry Gate
claims:
  - "PCB tools should carry electrical intent as explicit constraints, not only drawn geometry."
  - "DRC results are evidence for the design stage, but passing DRC is not the same as passing SI/PI compliance."
  - "Solver-ready PCB data should include stackup, net names, port intent, and geometry sanity checks."
  - "Allowed routing layers must be derived from the stackup; total board layer count is not the same as available signal routing layer count."
relationships:
  - "PCB Design Rule|is implemented in|KiCad"
  - "KiCad|runs|DRC"
  - "Stackup|supports|Controlled Impedance"
  - "Stackup|defines|Routing Layer"
  - "Reference Plane|supports|Return Current"
  - "Net Class|sets|PCB Design Rule"
  - "Differential Pair|uses|Net Class"
  - "Port Intent|supports|Geometry Gate"
  - "DRC|supports|Report Evidence"
---

# KiCad Design Rules

KiCad is the PCB/project artifact generator in the harness. The wiki-level
strategy is to keep electrical intent visible as constraints and metadata:
stackup, net classes, controlled-impedance assumptions, differential-pair
rules, geometry gates, and solver port intent.

## Design Rule Strategy

- Use net names that preserve interface/lane/polarity meaning.
- Preserve stackup and dielectric assumptions in the board file and manifest.
- Decide the stackup before routing and derive the allowed signal-routing
  layers from that stackup. Do not treat a four-layer PCB as four signal
  routing layers by default.
- For a conventional four-layer PCB, assume a starting point of `L1 signal /
  L2 GND / L3 PWR or GND / L4 signal`; route high-speed channels on L1/L4
  unless the strategy explicitly defines an interposer/package stackup with
  internal signal layers.
- Record the reference plane/layer for each high-speed route. A route without
  a continuous return path is only a topology proxy, even if geometry DRC passes.
- Emit port intent metadata when creating launch pads.
- Run DRC and classify violations as geometry blockers, manufacturing-rule
  blockers, or acceptable proxy limitations.
- Do not send a board to HFSS until DRC and geometry gates are reviewed.

## Typed Cards

Generated design-rule cards may be linked here after source intake. Baseline
execution rules for KiCad and solver handoff live in `CODEX.md`,
`README_AGENT.md`, and `.codex/skills/`; extracted engineering knowledge belongs
in `design_rules/`.
