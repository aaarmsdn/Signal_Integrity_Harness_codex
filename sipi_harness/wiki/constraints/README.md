---
graph: false
kind: wiki_control
---

# Constraints

This folder is intentionally empty in the shared baseline harness.

Spec-constraint cards should be generated or curated from governing evidence:
user-provided specifications, datasheets, internal requirements, Docling
conversion output, or `extract:spec-evidence` results. A constraint card can
drive pass/fail only when it preserves tier-0 source lineage and reviewed
numeric limits, equations, loading models, masks, or measurement methods.

Do not seed this folder with interface-looking placeholder constraints in the
shared repository. Missing constraints belong in the case-local
`strategy/design_strategy.yaml`, `wiki_fusion_input.json`, or evidence-gap
report until source extraction promotes them into reviewed typed cards.
