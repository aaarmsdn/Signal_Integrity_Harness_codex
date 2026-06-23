# Validation Rules

Validation is stage-based. A later stage must not claim compliance when an
earlier gate is incomplete unless a waiver explicitly marks the result as a
proxy or engineering estimate.

## Case Status

- `DRY_RUN_READY`: inputs and plan are valid, but EDA tools were not executed.
- `READY_FOR_LAYOUT`: strategy and evidence are sufficient to generate layout.
- `READY_FOR_EM`: layout geometry and port intents passed checks.
- `READY_FOR_BENCH`: EM result has a verified Touchstone file and benchmark inputs are ready.
- `PASS`: all required spec benches pass.
- `FAIL`: at least one required spec bench fails.
- `BLOCKED`: missing input, invalid artifact, tool failure, or unresolved human
  checkpoint.
- `PROXY`: generated evidence is useful for engineering, but not compliance.

## Strategy Gate

Pass requires:

- Governing spec or requirement source identified.
- Design strategy YAML exists.
- Spec compliance metric coverage exists and covers all requirement families
  discovered in the governing source, including frequency-domain metrics,
  impedance/TDR, crosstalk, skew/timing, jitter, transient waveform/eye/mask,
  BER/bathtub/contour, loading/source/receiver models, PDN/rail limits where
  applicable, and required report artifacts.
- Required benches, metrics, loading models, pass/fail equations, and reports
  are listed.
- Every coverage row is mapped to an implemented bench, proxy-only check,
  not-applicable rationale, or explicit blocker with source evidence.
- Figure/table evidence used for geometry has reviewer status.
- If a matching governing PDF or raw-source group exists, content-level
  extraction/fusion has run. `docling_hit_count=0` and
  `spec_evidence_hit_count=0` is a Strategy gate failure, not a layout input.
- README-only typed wiki folders are treated as scaffold, not evidence. A
  strategy may cite `design_rules/`, `constraints/`, or `stackups/` content only
  when reviewed cards with source lineage exist.

## Geometry Gate

Pass requires:

- No pad/ball/via overlap below configured clearance.
- No same-layer route crossing.
- `reports/kicad_same_layer_geometry.json` exists and reports `PASS` before
  HFSS handoff. This check is mandatory even if KiCad DRC and the preview image
  appear clean.
- Continuous adjacent reference layer for every high-speed channel.
- Reference-plane coverage is verified separately from launch tabs. Local GND
  port tabs or short reference patches do not satisfy channel return-path
  continuity.
- Routed centerline length and delay estimate recorded per lane.
- Delay skew within configured UI fraction, or waived.
- Port-intent JSON exists and matches generated nets/layers.

In End-to-End Goal Mode, this gate fails back into the PCB/package repair loop
instead of ending the task. Rerun deterministic/A* routing with revised lane
ordering, 45-degree diagonal routing enabled, adjusted keepouts, alternate
allowed signal layers, fanout changes, or strategy-approved spacing/stackup
changes until the gate passes or a concrete no-route blocker is recorded with
the attempted fixes.

Do not set `allow_diagonal: false` as the first repair for high-speed routes.
Turning diagonal routing off requires an explicit manufacturing/spec reason and
engineer approval.
A route result with missing routing settings, unapproved `allow_diagonal:
false`, or avoidable orthogonal-only/90-degree routing is a geometry gate
failure.

If a PCB/package repair removes the assigned reference plane/layer, fragments
it under the routed channel, or turns the candidate into signal-only routing,
the geometry gate fails before HFSS. Do not send that candidate to EM even if
same-layer crossings are fixed.

## HFSS 3D Layout Gate

Pass requires:

- AEDB is non-empty and has expected nets/layers.
- AEDB primitive overlap gate passes: no same-layer overlap between different-net
  polygon primitives after ODB/IPC/direct-AEDB conversion.
- The source PCB/package candidate passed the reference-plane coverage gate.
  HFSS may not be used to compensate for a layout with no continuous return
  path.
- Ports persist after AEDT reopen.
- Port count and expected order are recorded.
- Solve logs do not contain solver errors, stale locks, or invalid-solution
  messages.
- `analyze_setup()` truthy return is not used alone as proof.
- The requested native setup and sweep exist, and the sweep contains a real
  frequency table for the requested range. A visible `Sweep1` that exports only
  `LastAdaptive` is not a valid frequency sweep.
- Touchstone exists, is non-empty, has expected port markers, and has frequency
  data lines through the required stop frequency.

If solve succeeds but Touchstone export says solution data is unavailable,
inspect the port creation path. For KiCad/AEDB imports, the default valid path
is AEDB polygon-edge circuit ports (`--port-method edb_polygon_edge`) with a
signal polygon edge and local reference polygon edge. If the project used
coordinate `circuit` ports or `pin` ports, rebuild the import with
`edb_polygon_edge` before changing routing. Coordinate two-point ports are
manual/debug overrides only; when used, the terminal gate must prove that both
coordinates are on non-empty copper and avoid via holes/antipads.
For polygon-edge ports, the selected signal edge must be a short launch/pad edge
near the port intent coordinate. A long trace side edge or a sidewall edge on a
diagonal segment is invalid even if AEDT displays a port marker.
Do not repair this by switching to `edb_path_edge`. Path-edge creation is a
debug override only and is not a valid automatic handoff path.

If the setup/sweep exists by name but no requested frequency data exports,
delete and recreate the sweep before changing geometry or ports. Prefer
PyAEDT `Hfss3dLayout.create_linear_count_sweep(...)`; native AEDT fallback must
use the HFSS 3D Layout `Sweep3DLayout` template with
`Sweeps.Data = "LINC <start>GHz <stop>GHz <points>"`. Do not rely on generic
`RangeStart`/`RangeEnd` properties alone, because they can leave an empty HFSS
3D Layout sweep table.

If PyAEDT export and native AEDT `ExportNetworkData` both fail after a truthy
solve, classify the stage as `invalid_or_non_exportable_hfss3dlayout_ports`
or `touchstone_missing_unknown_export_failure`. This is a blocked EM result,
not a solved result. Do not synthesize S-parameters to unblock ADS; repair the
real HFSS 3D Layout handoff or stop with an explicit blocker.

## Bench Gate

Pass requires:

- Touchstone file copied or referenced using syntax valid for the selected benchmark tool.
- Touchstone is verified HFSS or measurement data, not a proxy substitute.
- Schematic, netlist, or post-processing connectivity is visually or machine verified.
- Loading model matches the governing spec.
- Every metric family marked `implemented` in the strategy coverage matrix has
  a corresponding dataset, extraction script, plot/report, and pass/fail or
  proxy status.
- Dataset, plot, and report paths resolve.
- Metrics are extracted from simulator datasets or documented post-processing,
  not invented from schematic intent.
- For N-lane crosstalk or eye benches, the bench covers the full S(2N)P channel
  and all required victim lanes. If the spec defines aggressor-inclusive
  conditions, every victim run includes all N-1 aggressors unless the spec
  defines a reduced method.
- ADS failure is blocked, not proxy. Do not synthesize proxy datasets or use a
  3-lane smoke check to close a multi-lane Bench stage.

## Metric Extraction

The strategy must define each metric. Common examples:

- Characteristic impedance: from TDR, line calculator, field solver, or
  S-parameter-derived impedance, with method stated.
- Insertion loss: victim transfer or S-parameter according to spec.
- Crosstalk: sum of aggressor contributions when the spec requires power-sum
  aggregation.
- Frequency-domain benchmark: S-parameter, transfer-function, impedance, or
  crosstalk metric calculated with the exact equation required by the spec.
- Transient-domain benchmark: waveform, eye, mask, jitter, or BER metric
  calculated with the exact stimulus and loading model required by the spec.
- VTF loss: receiver voltage divided by source voltage when the spec defines
  voltage transfer function.
- Eye mask: height and width measured at the target BER using the simulator's
  contour/bathtub data when the spec defines BER-dependent masks.

## Waivers

A waiver must include:

- Waiver ID.
- Owner.
- Date.
- Affected stage and metric.
- Reason.
- Evidence file paths.
- Whether the result may be used for engineering only or compliance.

Waivers do not turn a failed metric into a pass; they document why the flow can
continue and how the result should be interpreted.
