# Agent Lessons and Guardrails

This file records workflow mistakes observed during harness bring-up. Treat
these as product rules for future SI/PI tasks, not as notes for one case.

Whenever an agent fixes a wrong assumption, failed tool handoff, dirty dataset,
misdiagnosed blocker, or repeated workflow mistake, update this file or the
relevant skill/workflow document before committing. The entry should state the
failure symptom, the actual root cause, the corrected rule, and the evidence or
command that proved the fix. Do not rely on chat history or generated logs as
the only memory of the lesson.

## Routing and Geometry

- Do not claim A* routing unless the route was actually produced by an A* or
  equivalent deterministic router and `routing/route_result.json` records the
  waypoints, obstacles, layers, and settings.
- When a governing spec provides a bump map, ball map, pin table, or connector
  pinout, extract that evidence first and route from those coordinates.
- If the spec has no endpoint map, generate a synthetic case-local bump, ball,
  or pad map before routing. Mark it as `source_type: synthetic`, store the
  assumptions, and label downstream results as topology/proxy unless the spec
  allows arbitrary endpoint placement.
- A 4-layer design does not imply four signal routing layers. Choose the stackup
  first, reserve reference or power planes, and route only on the allowed signal
  layers.
- KiCad DRC is evidence, but it is not always the signoff authority for package,
  interposer, or ultra-fine-pitch proxy layouts. Separate true shorts/crossings
  from default manufacturing-rule violations and record any waiver.
- Prefer 45-degree diagonal routing for high-speed channels and avoid
  unnecessary 90-degree bends. If the geometry checker reports crossings or
  shorts in End-to-End Goal Mode, repair the route in the same PCB/package
  stage instead of stopping immediately.
- Do not disable diagonal routing as a repair shortcut. If diagonal routes
  create crossings, repair lane ordering, fanout, layer assignment, keepouts,
  spacing, endpoint pairing, or stackup assumptions while keeping
  `allow_diagonal: true`. Turning diagonal routing off requires an explicit
  manufacturing/spec reason and engineer approval.
- Route for minimum centerline length first. Select endpoint/lane ordering and
  allowed layer candidates to minimize total route length and obvious crossings
  before adding skew-matching meanders. Record any added matching length
  separately from the shortest-route baseline.
- If target impedance is known, choose an initial trace width/spacing from the
  stackup/material before routing and record the approximation. If pitch or
  clearance forces a different width, label the impedance as a pre-layout proxy
  and require HFSS/bench verification.
- If routes are length-sensitive, use actual centerline length from the routed
  waypoints, not endpoint spacing, and convert skew to UI fraction.
- A route that loses the channel reference plane is not a repair. Reference
  continuity is part of the design, not just the HFSS port launch. If a later
  routing attempt removes the assigned GND/reference plane or turns all
  available layers into signal routing, block the PCB/package stage and repair
  the stackup/routing contract before HFSS.

## HFSS 3D Layout Handoff

- Do not trust `analyze_setup()` alone. A valid HFSS stage requires a non-empty
  Touchstone file with the expected port count, port order, frequency range, and
  metadata.
- If solve succeeds but Touchstone export says no solution data is available,
  treat the port creation path as invalid until proven otherwise.
- A visible HFSS 3D Layout sweep name is not proof that frequency data exists.
  Delete and recreate empty sweeps with `create_linear_count_sweep(...)` or
  native `Sweep3DLayout` arguments using `Sweeps.Data = "LINC ..."` before
  assuming ports or geometry are broken.
- For direct KiCad-to-AEDB fallback, polygon/rectangle signal primitives often
  need AEDB-level edge ports. Location circuit ports may appear in the GUI but
  still fail network-data export.
- Demo v5 succeeded with real Gap polygon-edge ports after relaxing the
  terminal-edge length selector from 0.25 mm to 0.30 mm for short launch tabs,
  clearing only case-local stale `.asol_priv` / `*.semaphore` locks, closing
  leftover harness-started non-graphical AEDT sessions, and rerunning a clean
  solve/export. Wave edge ports and proxy S-parameters were not the fix.
- Do not flatten a spec-derived bump/ball/pin map into parallel straight launch
  rows after routing trouble. If the endpoint map records source bumps/balls
  but says the routed coordinates are proxy/fanout escapes, the PCB/package
  stage is blocked unless the engineer explicitly approves a proxy study.
- Do not use `edb_path_edge` as an automatic HFSS repair. It can place a port
  on a long trace side edge or the wrong Start/End edge. Fix the layout so
  `edb_polygon_edge` can select a short endpoint launch pad/tab edge.
- Keep source AEDB and work AEDB/AEDT paths distinct. Never overwrite the
  imported/source database with a generated work project of the same base name.

## Bench and ADS Verification

- Do not use a spec-neutral S-parameter fallback bench as a substitute for a
  known spec bench. The fallback is only for smoke, sanity, or proxy reporting
  when exact spec equations or loading models are unavailable.
- If VTF, XT, explicit R/C loading, eye/mask, BER contour, bathtub, or jitter
  requirements are present, the Bench stage is not complete until those exact
  metrics are implemented or the stage is explicitly blocked. Do not produce
  only an S-parameter fallback report and call the workflow complete.
- If the governing spec defines VTF, crosstalk power sum, loading networks,
  eye-mask, BER contour, or any other derived metric, implement those exact
  benches before making compliance claims.
- ADS schematic construction and netlist/simulator execution are separate
  checks. A passing script-generated dataset does not prove the schematic is
  connected correctly.
- For Touchstone-based benches, verify file location, filename syntax, port
  count, port ordering, and reference pin/ground handling before simulation.
- Eye/mask checks should use simulator contour variables at the required BER
  when available, not reconstructed density-image heuristics.
- ADS ChannelSim can produce two different-looking datasets for the same
  template: a schematic-run dataset under `workspace/data/` and a netlist smoke
  dataset under `netlist_runs/`. For report extraction, inspect `data/*.ds`
  first. The valid eye report variables are typically
  `ChannelSim1.TDM.Eye.EYE_L0`, `ChannelSim1.TDM.EyeMeasurements.EYE_L0`, and
  `ChannelSim1.TDM.Eye.BER.EYE_L0`. Do not mark BERContour missing just because
  the diagnostic `netlist_runs/*.ds` is sparse.
- Before ADS ChannelSim eye/BER simulation, check the verified Touchstone
  frequency grid. If the EM sweep is sparse, create a recorded
  `_eye_interp.sNp` using complex RI-domain interpolation and use it for the eye
  bench. This is allowed only after a verified real Touchstone exists; it is not
  a proxy substitute for missing EM data.
- For a lane-count N crosstalk or eye bench, use the full S(2N)P channel and
  run all required victim lanes. Include all N-1 aggressor lanes when the spec
  defines aggressor-inclusive metrics. A 3-lane `.s6p` example is only a smoke
  template.
- Do not rely on one ChannelSim run with multiple Eye Probe components for
  full-lane eye reporting. In demo testing, ADS accepted the netlist but
  `hpeesofsim` crashed or left dirty partial datasets after a few probes. The
  reliable pattern is one victim-lane ChannelSim run per lane, using the
  ADS-DE-exported ModelExtractor parameter set, then one combined N-panel report.
  A shortened hand-written Eye Probe line can produce trivial two-point density,
  so copy the full ADS-DE parameter set.
- If ADS fails, repair the real workspace/netlist/dataset/contour/report path
  or block the stage. Do not generate proxy datasets to make the workflow look
  complete.
- Fresh clones must not depend on ignored local ADS experiment scripts or
  repository-level interface adapters. If the strategy extracts source-backed
  metric families that generic checks cannot close, do not stop after
  `plan:bench-adapter`. If a verified Touchstone exists and the strategy has
  enough source-derived topology/equation/model data, run
  `bench:ads-from-strategy` so the case-local adapter contract is converted into
  ADS workspace/netlist/dataset/report attempts. Use `bench:ads-workspace` only
  as an ADS API/symbol/netlist smoke baseline.
- Check Touchstone electrical order before ADS. HFSS may export ports in
  physical order such as RX,TX per lane; the bench may require TX,RX per lane.
  Reorder with evidence and store `touchstone_port_order_summary.json` before
  running ADS.

## Reports and Claims

- Every stage must state whether its result is compliance evidence, engineering
  estimate, or proxy/sanity evidence.
- Do not let an old example generator silently define a new application. Use
  examples as templates only after the case strategy and evidence map have been
  made explicit.
- If the design depends on unreviewed figure extraction, synthetic maps, waived
  DRC, relaxed clearance, or spec-neutral benches, the final report must say so
  near the result summary.
- Raw source hits are not evidence by themselves. If `docling_hit_count=0` and
  `spec_evidence_hit_count=0` for a matching source document, stop before
  layout and run content extraction/fusion.
- README-only wiki folders are scaffolding, not knowledge. Do not let empty
  `design_rules/`, `constraints/`, or `stackups/` folders create a false sense
  that the strategy has source-backed design rules. The strategy must cite
  reviewed cards or case-local extraction artifacts.
- Do not use `llm-optimizer` during the baseline harness flow. Use it only for
  an explicit optimization study after the baseline strategy/layout/EM/bench
  path is valid.
