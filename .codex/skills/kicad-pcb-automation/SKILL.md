---
name: kicad-pcb-automation
description: Use KiCad CLI/MCP and harness scripts to create, inspect, validate, and report PCB/package layout artifacts with stackup, nets, constraints, DRC, geometry gates, and solver port-intent metadata for SI/PI workflows.
---

# KiCad PCB Automation

Use this skill for PCB/package generation or inspection with KiCad.

## Role

KiCad is the layout/project artifact stage. It should not silently decide the
electrical strategy. Before creating geometry, confirm the case has:

- spec evidence under `outputs/<case>/spec_evidence/`
- `strategy/design_strategy.yaml`
- pre-PCB wiki strategy PDF
- stackup/material assumptions
- allowed routing layers derived from the stackup, not just total PCB layer count
- target nets/lanes and port intent requirements
- endpoint map evidence: a spec-derived bump/ball/pin map, or a case-local
  synthetic bump/ball/pad map with explicit assumptions

## Required Outputs

For each PCB/package stage, produce or update:

- `.kicad_pro`, `.kicad_pcb`, and `.kicad_sch` when applicable
- case `manifest.json`
- `simulation/hfss3dlayout_port_intents.json`
- `reports/kicad_layout_preview.png` or equivalent layout preview image for
  human review
- DRC report or explicit reason DRC was skipped
- geometry gate results: pad/via/trace clearance, same-layer crossing/short checks, routed length, delay skew, reference availability
- `reports/kicad_same_layer_geometry.json` from
  `npm run check:kicad-geometry -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_same_layer_geometry.json --manifest <case-dir>\manifest.json`
- `reports/port_launch_clearance.json` from
  `npm run check:port-launch -- --board <board.kicad_pcb> --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --summary <case-dir>\reports\port_launch_clearance.json`
- `01_pcb_package_report.pdf` through `scripts/generate_stage_pdf_reports.py`
- `routing/route_plan.json` and `routing/route_result.json` when nets are routed from a ball map, pad map, connector map, or pin table
- `routing/*_map.json` when a synthetic bump/ball/pad map is generated because
  the governing spec did not provide one

## MCP Versus Skill

Use KiCad MCP/CLI for operations. Use this skill as the procedural memory:
what to create, what to check, and what metadata must be preserved for HFSS and
ADS. MCP is the tool surface; this skill is the workflow contract.

## Hard Rules

1. Do not use old case generators as generic PCB generators.
2. Preserve electrical intent in net names, net classes, stackup, constraints,
   and port intent JSON.
3. Choose the PCB/package stackup before routing. The allowed routing layers
   are the signal layers after reserving reference/power layers. For example,
   a normal 4-layer PCB should usually be treated as `L1 signal / L2 GND /
   L3 PWR or GND / L4 signal`; route on L1/L4 unless the strategy explicitly
   defines an interposer/package stackup where inner layers are signal layers.
   Do not interpret "maximum 4 layers" as permission to route on all 4 layers.
4. Each high-speed route must have an adjacent or clearly assigned reference
   plane/layer in the manifest and port intent. If the stackup cannot provide
   a continuous return path, mark the board as a proxy and do not send it to
   HFSS as a compliance candidate.
   Local GND launch tabs or port-reference patches do not satisfy this rule.
   They help the port launch, but they are not the channel return path. If a
   repair attempt removes or fragments the assigned reference plane, the
   PCB/package stage fails and must be rerun before HFSS.
5. Do not invent routing paths by eyeballing geometry. When endpoints come from
   a ball map, pad map, connector pinout, or pin table, route with a deterministic
   router such as `scripts/astar_grid_router.mjs`,
   `scripts/create_generic_channel_case.py`, or a KiCad-native equivalent.
   The generated route result must be saved and cited in the manifest.
   If no map is provided by the governing spec or user input, generate a
   synthetic bump/ball/pad map first. Save the map as a case artifact with
   `source_type: synthetic`, pitch, row/column coordinates, lane mapping,
   module/side placement, and assumptions. Route from that artifact, not from
   unstated coordinates.
   If a spec/table/figure map exists, do not flatten it into straight parallel
   launch rows after routing trouble. Route from the extracted map itself, or
   create a reviewed fanout/escape stage that preserves source bump/ball/pin
   records and clearly blocks compliance until reviewed. A map that records
   source bumps/balls/pins but marks routed coordinates as proxy/fanout escape
   must not proceed to HFSS as a valid candidate.
   For new general channel/package requests, prefer:
   `npm run create:channel-case -- --case-dir <case-dir> --case-name <case-name> --interface <interface> --package-class <package-class> --lane-count <n> --data-rate-gbps <rate> --channel-length-mm <length-mm> --layer-count <layers> --dk <Dk> --df <Df> --bump-pitch-um <pitch> --target-impedance-ohm <Z0> --overwrite`.
   Add `--endpoint-map <path>` when reviewed spec/user coordinates are
   available.
6. For A* routing, obstacles must include existing pads, forbidden keepouts,
   already-routed traces on the same layer, board edges, and clearance inflation
   by at least `trace_width/2 + clearance`.
   Set `allow_diagonal: true` unless the manufacturing rule or design strategy
   explicitly prohibits diagonal traces. Diagonal steps must use Euclidean or
   octile costs, and the router must prevent corner-cutting through inflated
   obstacles. Do not turn diagonal routing off merely to make a failed route
   pass; repair lane order, fanout, layer choice, spacing, keepouts, endpoint
   pairing, or stackup assumptions while keeping `allow_diagonal: true`.
   A route result with missing route settings, `allow_diagonal: false` without
   explicit approval, or avoidable orthogonal-only/90-degree high-speed routing
   is a PCB/package gate failure.
   Optimize for shortest routed centerline length first, before adding any
   length-matching detours. Endpoint/lane ordering should minimize total
   Manhattan/octile distance and obvious crossings before routing. The route
   result must record actual centerline length; do not use nominal module gap
   or endpoint spacing as the lane length.
   Never replace a failed route with a straight-line route unless that straight
   line is the actual A* result from the reviewed endpoints and passes all
   geometry gates. If A* cannot route a lane, keep the lane blocked and repair
   lane order, fanout, layer assignment, keepouts, spacing, or stackup.
7. For multi-lane buses, route lanes in an explicit order and reserve accepted
   routes as obstacles for later lanes. After routing, compute routed length,
   spacing, crossings, and delay skew from the actual route result.
   If skew matching is required, add meanders only after the shortest valid
   routes pass the geometry gate, and record the added length separately.
8. If a target impedance exists in the strategy or spec evidence, choose an
   initial KiCad route width/spacing from stackup/material before routing. Use
   a documented line calculator, 2D extractor, field-solver rule, or rough
   microstrip/stripline estimate. Record `target_impedance_ohm`,
   `estimated_z0_ohm`, width/spacing, formula/model, reference layer, Dk/Df,
   copper thickness, and assumptions in the route request/result and manifest.
   If pitch/clearance forces a width that misses the target, keep the geometry
   manufacturable, mark the impedance result as a pre-layout estimate/proxy,
   and require HFSS/bench verification before any compliance claim.
   The generic helper is:
   `npm run estimate:trace-width -- --target-ohm <Z0> --er <Dk> --height-mm <h> --pitch-mm <pitch> --clearance-mm <clearance> --output <case-dir>\routing\trace_width_estimate.json`.
9. Run the repository same-layer geometry checker on every generated
   `.kicad_pcb` before HFSS handoff:
   `npm run check:kicad-geometry -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_same_layer_geometry.json --manifest <case-dir>\manifest.json`.
   This is mandatory even when the preview image looks clean and even when
   KiCad DRC reports no violations. Any different-net same-layer crossing,
   same-layer short, trace-to-pad/via short, or pad/via overlap is a hard
   blocker for solver handoff unless the case is explicitly recorded as
   proxy/blocked and not a valid EM candidate.
   In End-to-End Goal Mode, a geometry violation is not the final answer. Repair
   the route within the PCB/package stage until the checker passes or until a
   concrete routing blocker is recorded with attempted alternatives. Required
   repair attempts include rerun A* with updated lane ordering, diagonal routing
   enabled, larger keepouts, adjusted escape/fanout, alternate allowed signal
   layer, or revised stackup/spacing assumptions. Only stop after the repair
   loop has produced evidence that no valid route exists under the current
   constraints.
10. KiCad DRC is required when available, but it is not an automatic blocker for
   package/interposer or ultra-fine-pitch proxy layouts if KiCad's default
   manufacturing constraints are stricter than the intended technology. Separate
   true electrical/geometry errors from default-rule violations. Do not send a
   board to HFSS if DRC reports real shorts/crossings unless the manifest marks
   the board as a proxy and records the reason. Annular ring, hole clearance,
   and default netclass errors may be waived only with explicit geometry-gate
   evidence and a waiver note.
11. HFSS 3D Layout port intents must support AEDB polygon-edge ports by
   default. Emit `positive_x/positive_y` at the intended signal launch, signal
   net/layer, reference net/layer, expected order, and optional edge-selection
   limits. Use `edb_polygon_edge` unless an explicit case override selects
   coordinate `circuit` or `pin` ports. A failed launch/edge placement gate is a
   hard EM handoff blocker because AEDT can show bad ports while exporting no
   network data.
12. After KiCad-to-AEDB conversion, require the AEDB primitive overlap gate to
   pass before HFSS solve. Converter-created launch pads, via pads, junction
   pads, trace-outline polygons, or port tabs can short lanes even when the
   source KiCad checker passed. Any same-layer different-net primitive overlap
   is a hard blocker.
13. Convert length mismatch to delay skew and UI fraction for the active data
   rate.
14. If a generated board is based on a spec figure, the coordinate transform must
   reference the extracted figure/table evidence.
15. After KiCad/package generation, render a layout preview image and show it
    to the engineer in Stage Review Mode before HFSS handoff:
    `npm run render:kicad-preview -- --board <board.kicad_pcb> --output <case-dir>\reports\kicad_layout_preview.png --manifest <case-dir>\manifest.json`.
    The image is required for human review, but DRC, route records, and geometry
    gates remain the authoritative machine-readable evidence.

## A* Routing Contract

Before routing, resolve endpoint sources in this order:

1. Tier-0/spec-derived bump, ball, pin, connector, or package map.
2. User-provided map/model with recorded provenance.
3. Synthetic case-local map generated from request parameters and clearly
   marked as proxy/synthetic.

When using option 3, record that compliance is blocked or proxy-only until the
governing spec/user approves the endpoint placement.

Use this contract before calling KiCad MCP `route_trace` for nontrivial routes:

```json
{
  "grid_mm": 0.025,
  "trace_width_mm": 0.04,
  "clearance_mm": 0.04,
  "allow_diagonal": true,
  "length_weight": 1,
  "bend_penalty_mm": 0.003,
  "target_impedance_ohm": 50,
  "impedance_estimate": {
    "model": "microstrip_or_stripline_pre_layout",
    "estimated_z0_ohm": 50,
    "reference_layer": "L2_GND"
  },
  "bounds": { "x1": 0, "y1": 0, "x2": 10, "y2": 10 },
  "start": { "x": 1, "y": 1 },
  "goal": { "x": 9, "y": 9 },
  "obstacles": [
    { "x1": 2, "y1": 2, "x2": 3, "y2": 8 }
  ]
}
```

Run:

```powershell
npm run estimate:trace-width -- --target-ohm 50 --er 4.3 --height-mm 0.1 --pitch-mm 0.13 --clearance-mm 0.015 --output <case-dir>\routing\trace_width_estimate.json
npm run route:astar -- --input <case-dir>\routing\route_request.json --output <case-dir>\routing\route_result.json
```

For dense bump-map-to-bump-map or pad-map-to-pad-map package examples, a
case-specific deterministic router can be used directly after the map artifact
is generated or extracted:

```powershell
python sipi_harness\scripts\<case_specific_router>.py --out-dir <case-dir>
```

Only pass the returned `waypoints` into KiCad route creation. If no path exists,
change constraints, layer assignment, escape strategy, or stackup; do not draw
an arbitrary crossing route.
