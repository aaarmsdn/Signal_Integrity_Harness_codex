---
graph: false
kind: wiki_control
---

# Purpose

This wiki exists to turn SI/PI source material into reusable engineering
strategy for package, PCB, interconnect, and PDN design.

The wiki should answer:

- What design constraints matter for the requested electrical interface?
- Which SI/PI mechanisms dominate the design risk?
- Which geometry, stackup, launch, return-path, and PDN choices are supported
  by source evidence?
- Which EM and circuit verification benches are required before claiming
  compliance?
- Which assumptions are provisional, proxy-only, or contradicted by stronger
  evidence?

The wiki is not a chat transcript and not a tool execution log. It is the
compiled design-knowledge layer used before KiCad, HFSS 3D Layout, ADS, or
other tools are run.

Repository-shipped typed cards are generic seed cards and schemas, not a
complete design handbook and not application-specific compliance evidence.
For each new task, generate or update case-local strategy from:

- governing spec evidence extracted from the active PDF/datasheet,
- Docling/spec-evidence content extracted from `wiki/raw/`,
- current web/user reference intake,
- reusable generic cards from this wiki.

Do not treat a raw-source group name, a preloaded generic card, or an old
example case as enough evidence to route, simulate, or claim compliance.
