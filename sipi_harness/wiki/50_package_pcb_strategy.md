---
graph: false
kind: hub_page
id: wiki_package_pcb_strategy
topic: package_pcb_strategy
summary: "Package and PCB strategy connects stackup, launch, pad, via, escape routing, reference planes, and length matching to SI/PI risk controls."
concepts:
  - Package
  - PCB
  - Stackup
  - Pad
  - Via
  - Launch
  - Escape Routing
  - Reference Plane
  - Geometry Gate
  - Length Matching
  - Port Intent
claims:
  - "Package and PCB geometry must be checked before solver handoff: pads, vias, traces, launches, crossings, and reference paths."
  - "Port intent should be emitted by the board generator because it knows the intended signal pad and reference."
  - "Length matching should be stored as actual routed centerline length and delay estimate per lane."
relationships:
  - "Package|uses|Stackup"
  - "PCB|uses|Stackup"
  - "Pad|forms|Launch"
  - "Via|forms|Launch"
  - "Escape Routing|uses|Via"
  - "Reference Plane|supports|Return Path"
  - "Geometry Gate|checks|Pad"
  - "Geometry Gate|checks|Via"
  - "Geometry Gate|checks|Escape Routing"
  - "Length Matching|checks|Escape Routing"
  - "Port Intent|defines|Launch"
---

# Package and PCB Strategy

Package and PCB layout strategy translates requirements into physical geometry.
This wiki page describes the design knowledge. The exact tool execution belongs
in `CODEX.md`, `README_AGENT.md`, and skills.

## Geometry Gate

Before EM extraction, check:

- pad and ball edge clearance
- via edge clearance and annular ring/manufacturing constraints
- trace-to-trace spacing and same-layer crossing risk
- broadside overlap on adjacent signal layers
- reference plane continuity and return via availability
- launch geometry and port reference availability
- actual routed length and delay skew per channel

## Port Intent

The layout generator should emit port intent metadata while it creates pads or
launches. A later solver import should not guess arbitrary line ends if the
design generator can state signal net, reference net/layer, coordinate, port
type, impedance, and expected order.

## Typed Cards

Stackup, material, routing, spacing, length-matching, and reference-plane cards
should be generated under `stackups/` and `design_rules/` from the active raw
source set or engineer-approved references. The shared baseline does not ship
final stackup or design-rule cards.
