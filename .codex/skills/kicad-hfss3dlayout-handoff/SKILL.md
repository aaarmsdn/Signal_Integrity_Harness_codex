---
name: kicad-hfss3dlayout-handoff
description: Convert KiCad PCB/package artifacts into Ansys HFSS 3D Layout/AEDB projects using explicit port-intent JSON, direct KiCad-to-AEDB fallback, circuit/pin port creation, reopen verification, solve setup, and Touchstone export.
---

# KiCad to HFSS 3D Layout Handoff

Use this skill when moving a KiCad board/package channel into HFSS 3D Layout.

## Flow

1. Start from a case folder with KiCad board/project and manifest.
2. Require `simulation/hfss3dlayout_port_intents.json`.
3. Export KiCad to ODB++/IPC-2581 when available.
4. Import into HFSS 3D Layout.
5. If native import creates empty AEDB or loses geometry, use direct
   KiCad-to-AEDB fallback.
6. Create ports from port intents using AEDB polygon-edge circuit
   ports by default:
   - Default method: `edb_polygon_edge`. Select the signal polygon edge near the
     intended launch and the local reference primitive/edge on the reference
     net/layer.
   - `edb_path_edge` is a debug override only. Do not use it as an
     automatic retry: it can attach to a long trace side edge or to the wrong
     Start/End edge and then produce a visible-but-invalid port.
   - Use coordinate `circuit` location ports or `pin` ports only as explicit
     overrides after manual/tool evidence shows the imported pin/coordinate
     placement is correct. These methods can place terminals at the wrong
     coordinates after KiCad/AEDB import.
   - If the closest facing reference point is blocked by a via hole or antipad,
     select the nearest adjacent solid reference edge/primitive while keeping
     the port local. Do not first distort the routing topology to make the port
     work.
7. Save and reopen AEDT project.
8. Verify layers, nets, primitive count, port count/order, and setup metadata.
   Also verify post-conversion AEDB geometry: same-layer different-net
   primitive overlaps are hard blockers, even if the source KiCad DRC passed.
   Verify the electrical return-path contract before import/solve: every
   high-speed signal route must have the assigned continuous reference
   plane/layer from the strategy. Local GND tabs or port-reference patches do
   not replace this channel reference. If the candidate was rerouted without a
   real reference plane, block HFSS and return to PCB/package generation.
9. Create solve setup and sweep from strategy/wiki rules.
10. Solve and export Touchstone.
11. Validate solver completion from evidence, not from API return values alone.
12. If EM export remains blocked, repair the real geometry/import/port/solve
    path until a verified Touchstone exists, or stop with an explicit blocker.

When opening an AEDB in `Hfss3dLayout`, do not force a generic design name
such as `PCB` unless that design already exists. Let AEDT select the imported
EDB cell, or use the imported design name from the import summary. Forcing a
new design name can create an empty HFSS 3D Layout design with no boundary
module ports, leading to `analyze_setup()` returning success while Touchstone
export fails with no solution data.

## Port Intent Contract

Each port intent should include:

- name
- type: `edb_polygon_edge` by default; `edb_path_edge`, `circuit`, or `pin`
  only for explicit debug overrides
- signal net
- reference net
- positive layer
- negative/reference layer when applicable
- positive coordinate or pad/ball identifier
- reference layer/net plus local reference geometry selector for edge-port
  creation. Prefer reference primitive/edge selection metadata over reference
  point coordinates.
- expected impedance
- expected port order

Do not infer ports from arbitrary trace endpoints if the board generator can
emit launch/pad metadata. For pad/ball/bump launch structures, the default
placement rule is `polygon_edge_signal_to_local_reference_edge`: signal launch
polygon edge paired with adjacent reference-net polygon edge. Use
`two_point_circuit_port_ref_terminal_on_solid_plane` only for explicit
coordinate-port override/debug flows.

The positive edge must be a short terminal launch edge, launch pad, or launch
tab at the intended endpoint. Never accept the long side of the routed trace as
the signal port edge. If no short edge exists, block EM handoff and return to
PCB/package generation to add a non-overlapping endpoint launch pad/tab.

Run:

```powershell
npm run check:port-launch -- --board <board.kicad_pcb> --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --summary <case-dir>\reports\port_launch_clearance.json
```

Treat a failed port-launch check as an EM handoff blocker.

## Required Polygon-Edge Port Rule

This is the most common HFSS 3D Layout failure mode in this harness. Treat it
as a hard gate.

Do not trust any of these by themselves:

- port labels visible in the GUI
- `app.port_list` containing the expected names
- `analyze_setup()` returning `True`
- result folders containing partial `.planar` files

The handoff is valid only when a non-empty Touchstone exports with the expected
port count, order, and frequency range.

For KiCad/AEDB imports, use polygon/primitive edge circuit ports as the normal
path. The known-good pattern is a small signal launch polygon edge paired with a
nearby local GND/reference polygon edge. Coordinate circuit ports can be kept as
debug tools, but they are not the default because PyAEDT/AEDT can misplace
manual circuit-port coordinates after import.

The selected signal edge must be terminal-like: short, local to the port-intent
coordinate, and on the launch/pad end of the net. Do not attach a port to a long
diagonal or horizontal trace side edge just because it is nearest to the intent
coordinate. If no short local launch edge exists, fail the import and add/fix a
small non-overlapping launch tab or pad in the source layout.

Default terminal-edge limits:

- maximum selected edge length: 0.30 mm
- maximum distance from port intent coordinate to selected edge: 0.05 mm

These limits intentionally reject cases where an edge selector would choose a
long routed-trace side edge for a data lane while still accepting short launch
tabs around 0.26 mm observed in working edge-port cases. Override them only
with explicit case evidence.

Preferred polygon-edge import command pattern:

```powershell
npm run import:hfss3dlayout -- --port-method edb_polygon_edge --edge-port-type Gap ...
```

Coordinate `circuit` or `pin` import methods are blocked by default. If a
manual/debug experiment truly needs them, the command must explicitly include
`--allow-coordinate-port-override` and the report must explain why polygon-edge
ports were not used. Do not run a coordinate-port first attempt for normal
package/channel cases.

Primitive-edge example for polygon/path imports:

```python
port = h3d.create_edge_port(
    assignment="SIGNAL_PORT_TAB",
    edge_number=selected_signal_edge,
    is_circuit_port=True,
    reference_primitive="GND_PORT_TAB",
    reference_edge_number=selected_reference_edge,
)
if not port:
    raise RuntimeError("Failed to create exportable HFSS 3D Layout circuit port")
```

Coordinate-port override example, for manual/debug use only:

```python
oeditor = h3d.modeler.oeditor
oeditor.CreateCircuitPort([
    "NAME:Location",
    "PosLayer:=", "F.Cu",
    "X0:=", "2.000mm",
    "Y0:=", "2.540mm",
    "NegLayer:=", "In1.Cu",
    "X1:=", "1.895mm",  # nearby solid GND; outside via drill/antipad keepout
    "Y1:=", "2.540mm",
])
```

When selecting a local reference edge or coordinate override, scan candidates
near the signal launch:

1. Start with the closest facing point on the reference plane or GND tab.
2. Reject it if it is inside a via drill, antipad, or via radius plus clearance.
3. Try adjacent solid reference-copper candidates while keeping the terminal
   span local.
4. Record the selected primitive/edge or point, terminal span, nearest via
   distance, and clearance in `reports/port_launch_clearance.json`.

If `ExportNetworkData` says `solution data is not available` after a true solve,
first assume the ports or setup are non-exportable. Rebuild with
`edb_polygon_edge` if any coordinate/pin port path was used; otherwise repair
the primitive edge/reference edge selection, rerun `check:port-launch`,
re-import, re-solve, and export again. Do not generate proxy S-parameters.
Do not "fix" this by rerouting into a signal-only or no-reference-plane board.
Any reroute after HFSS failure must preserve stackup, continuous reference
coverage, impedance intent, and diagonal-routing rules from the strategy.
If ports and native setup/sweep registration are correct, inspect for stale
AEDT result locks before changing the port method. In successful demo recovery,
Gap polygon-edge ports were already valid; export failed because stale
case-local `.asol_priv` / `*.semaphore` state and leftover non-graphical AEDT
processes invalidated result data. Close only harness-started non-graphical
`ansysedt.exe -grpcsrv -ng` sessions for the case, remove only case-local
semaphore files under that AEDT result directory, rerun the same Gap
polygon-edge solve in a clean working directory, and then verify a non-empty
Touchstone. Trying Wave edge ports did not fix the export in that case.

## Known-Good Touchstone Extraction Playbook

Use this playbook before trying new HFSS port experiments. It captures the
successful harness pattern observed after multiple failed coordinate/pin-port
attempts.

### Preconditions

- KiCad/package geometry gate passed.
- Post-conversion AEDB primitive overlap gate passed.
- Every high-speed route has a continuous assigned reference plane/layer.
- `simulation/hfss3dlayout_port_intents.json` exists and uses
  `type: edb_polygon_edge` or omits type so the importer defaults to
  `edb_polygon_edge`.
- No `negative_x` / `negative_y` fields are present in edge-port intents.
  Coordinate terminals are debug overrides only.
- Port launch geometry uses small non-overlapping signal launch tabs and local
  GND/reference tabs or a local solid reference edge. Do not place a signal
  launch tab so it overlaps another lane after AEDB polygon conversion.

### Command Sequence

Run from `<repo>\sipi_harness` with the active case paths:

```powershell
npm run check:kicad-geometry -- --board <case-dir>\layout\<board>.kicad_pcb --output <case-dir>\reports\kicad_same_layer_geometry.json --manifest <case-dir>\manifest.json

npm run check:port-launch -- --board <case-dir>\layout\<board>.kicad_pcb --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --summary <case-dir>\reports\port_launch_clearance.json

npm run import:hfss3dlayout -- --odb <case-dir>\simulation\hfss3dlayout\<case>_odb.zip --kicad-board <case-dir>\layout\<board>.kicad_pcb --project <case-dir>\simulation\hfss3dlayout\<case>_edge.aedt --summary <case-dir>\simulation\hfss3dlayout\<case>_import_summary.json --port-intents <case-dir>\simulation\hfss3dlayout_port_intents.json --port-method edb_polygon_edge --edge-port-type Gap --prefer-direct-edb --version 2025.1 --non-graphical --overwrite

npm run solve:hfss3dlayout-touchstone -- --project <case-dir>\simulation\hfss3dlayout\<case>_edge.aedt --version 2025.1 --expected-version 2025.1 --non-graphical --setup Setup_5xNyq --sweep Sweep_5xNyq_121 --adaptive-ghz <stop-ghz> --start-ghz 0.01 --stop-ghz <stop-ghz> --points 121 --sweep-type Fast --touchstone <case-dir>\simulation\hfss3dlayout\<case>.sNp --summary <case-dir>\simulation\hfss3dlayout\<case>_solve_summary.json
```

The exact script arguments can differ by case, but do not change the method:
Gap polygon-edge ports first, native setup/sweep registration, then explicit
Touchstone validation.

Do not use `npm run export:hfss3dlayout-native` as the normal solve path. That
command is an existing-solution export/retry helper around
`run_aedt_native_export.py`; it requires an already solved design and an
explicit design name. For new EM solves use `solve:hfss3dlayout-touchstone`.

### Port Selection Rules That Made Export Work

- Select a short terminal-like signal polygon edge near the intended port
  coordinate. The observed working launch-tab edge length was approximately
  0.26 mm; the default selector limit is therefore 0.30 mm.
- Reject long trace side edges, diagonal trace sidewalls, or any edge whose
  center is not local to the port intent. These can visually create ports but
  attach to the wrong physical terminal.
- Pair the signal edge with a nearby local GND/reference primitive edge. The
  reference edge must be solid copper, not a via drill/antipad/clearance hole.
- If the nearest facing reference point is inside a via hole or antipad, keep
  the signal launch fixed and select the nearest adjacent solid reference edge.
- Use `Gap` edge ports first. Do not switch to `Wave` ports as a blind repair;
  a previous successful recovery kept Gap polygon-edge ports unchanged.

### Setup/Sweep Rules That Made Export Work

- Create or repair the HFSS 3D Layout setup in the native AEDT design tree.
  Do not rely only on PyAEDT object creation or visible tree names.
- Delete and recreate the requested sweep if it is visible but has no frequency
  row. HFSS 3D Layout can show a sweep name while only `Last Adaptive` has data.
- Use a real HFSS 3D Layout sweep table such as:

```python
h3d.create_linear_count_sweep(
    setup="Setup_5xNyq",
    unit="GHz",
    start_frequency=0.01,
    stop_frequency=stop_ghz,
    num_of_freq_points=121,
    name="Sweep_5xNyq_121",
    save_fields=False,
    save_rad_fields_only=False,
    sweep_type="Interpolating",
)
```

- Export only from the requested `Setup : Sweep`. Do not export `Last
  Adaptive` as the channel handoff; it is usually one frequency point.

### Success Criteria

All of these must be true before ADS:

- AEDT project reopens with the expected port count and port names.
- Native `SolveSetups.GetSetups()` includes the requested setup.
- Native `SolveSetups.GetSweeps(setup)` includes the requested sweep.
- The requested sweep, not only `Last Adaptive`, has report-visible data.
- A non-empty `.sNp` exists.
- The Touchstone parser/check confirms expected port count, order, units, and
  frequency range.

If any item fails, stay in HFSS repair. Do not create proxy S-parameters and do
not proceed to ADS compliance.

## AEDB Primitive Geometry Gate

Run a post-conversion AEDB primitive overlap gate after ODB/IPC/direct-AEDB
import and before HFSS solve. This catches failures that KiCad checks can miss:
converter-created rectangular launch pads, via pads, junction pads, trace
outline polygons, or port tabs can overlap another lane after conversion.

Hard blocker:

- same-layer overlap between different-net polygon primitives
- launch/via pad polygon touching or covering another signal polygon
- port tab/edge polygon shorting two nets

If this gate fails, fix the source layout or converter geometry and rebuild the
AEDB. Do not solve the shorted `.aedt`, and do not rely on a clean KiCad preview
as evidence.

## HFSS Sweep Rule

Use the active data rate:

```text
fN = data_rate / 2
default_stop = 5 * fN
```

Default point guidance:

- smoke/import check: 10-30 frequency points
- engineering channel check: 101-401 points through at least `5*fN`
- resonant or mask-sensitive designs: segmented/adaptive sweep with finer
  spacing around expected resonances, anti-resonances, crosstalk peaks, and
  spec limit frequencies

Record whether the run is a smoke test, engineering estimate, or compliance
bench. Never claim compliance from a smoke sweep.

In Stage Review Mode, pause before running the solve and show the engineer the
setup review:

```powershell
cd <repo>\sipi_harness
npm run prompt:stage-review -- --stage hfss --case-dir <case-dir> --data-rate-gbps <rate> --sweep-type Fast --points <n>
```

Do not cross this gate until the strategy, board/database, port intent, port
method, expected port count, sweep settings, Touchstone target, and proxy versus
compliance status are reviewable.

## Native Setup and Sweep Registration Gate

HFSS 3D Layout can import valid ports and still have no exportable solution if
the setup/sweep was not registered in the native AEDT design. This happened in
practice with a polygon-edge port project: the ports were correct, but `Setup1`
was missing from the native solution tree, so `ExportNetworkData` had no
solution data.

Before solve/export, inspect the native `SolveSetups` module, not only PyAEDT
objects:

```python
solve_setups = h3d.odesign.GetModule("SolveSetups")
setups = list(solve_setups.GetSetups())
if "Setup1" not in setups:
    h3d.create_setup(name="Setup1", setup_type="HFSS3DLayout")
    h3d.save_project()

sweeps = list(solve_setups.GetSweeps("Setup1"))
# Repair the requested sweep even if a visible Sweep1 exists. HFSS 3D Layout
# can show Sweep1 while its sweep table has no frequency row, which exports
# only "Last Adaptive".
if "Sweep1" in sweeps:
    h3d.get_setup("Setup1").delete_sweep("Sweep1")
h3d.create_linear_count_sweep(
    setup="Setup1",
    unit="GHz",
    start_frequency=0.01,
    stop_frequency=6,
    num_of_freq_points=121,
    name="Sweep1",
    save_fields=False,
    save_rad_fields_only=False,
    sweep_type="Interpolating",
)
h3d.save_project()

solution_names = list(solve_setups.GetAllSolutionNames())
if not any(name.startswith("Setup1 : Sweep1") for name in solution_names):
    raise RuntimeError("HFSS 3D Layout setup/sweep is not registered natively")
```

For native AEDT `SolveSetups.AddSweep` scripts that do not use PyAEDT, use the
HFSS 3D Layout sweep template form. Do not use generic `RangeType`,
`RangeStart`, and `RangeEnd` properties because they can create an empty sweep
table:

```python
from ansys.aedt.core.generic.data_handlers import _dict2arg
from ansys.aedt.core.modules import setup_templates
import copy

props = copy.deepcopy(setup_templates.Sweep3DLayout)
props["Sweeps"]["Variable"] = "Freq"
props["Sweeps"]["Data"] = f"LINC 0.01GHz {stop_ghz:g}GHz 121"
props["FreqSweepType"] = "kInterpolating"
arg = ["NAME:Sweep1"]
_dict2arg(props, arg)
solve_setups.DeleteSweep("Setup1", "Sweep1")  # if it already exists
solve_setups.AddSweep("Setup1", arg)
```

After solving, probe the requested `Setup : Sweep` for report-visible solution
data before export. A visible sweep name is not sufficient: AEDT can list
`Setup_5xNyq : Sweep_5xNyq_121` while only `Setup_5xNyq : Last Adaptive`
contains data at the adaptive frequency. Do not export from `Last Adaptive` for
channel handoff because it is a single-frequency adaptive result. If the sweep
probe fails, classify the stage as `hfss3dlayout_sweep_name_exists_but_no_solution_data`
and repair solve execution before ADS.

If this gate fails, do not keep trying Touchstone export and do not rebuild
ports first. Repair native setup/sweep registration or sweep solve execution,
save, reopen, and only then run solve/export. A correct polygon-edge port
project with no setup or no solved sweep data is a setup/solve blocker, not a
port blocker.

## Required Reports

After import/solve, update:

- import summary JSON
- solve summary JSON
- Touchstone path and port order metadata
- `02_em_solve_report.pdf`
- case manifest status

## Solve Validation Gate

Do not treat a PyAEDT `analyze_setup()` truthy return as proof that HFSS solved
successfully. Before ADS handoff, require all of the following:

- AEDT message/log files contain no solver `error`, `Out of memory`, stale
  `.asol_priv` lock, or invalid solution messages.
- Result `profile.txt` does not end with `Status=Error`.
- Adaptive convergence status and final delta are recorded. If the solve did
  not converge, mark the result as engineering/proxy unless the strategy
  explicitly accepts that setup.
- The requested sweep completed through at least the strategy stop frequency.
- A non-empty Touchstone file exists, with the expected port count, port order,
  and frequency range.
- The requested sweep, not only `Last Adaptive`, has report/export-visible
  frequency data.

If any item fails, stop before ADS compliance. Record `HFSS_INCOMPLETE` or
`TOUCHSTONE_MISSING` in the case manifest and do not create proxy compliance
results.

For non-graphical automation, close the AEDT desktop session after import,
solve, export, or failure. Repeated failed attempts must not leave stale
`ansysedt.exe -grpcsrv -ng` processes. Leave GUI sessions open only when the
engineer explicitly requested visual inspection.

## Failure Mode: Solved True, No Export Data

If AEDT reports a completed solve but `ExportNetworkData` or
`export_touchstone()` says solution data is not available, assume the port
creation path is invalid until proven otherwise. A common direct KiCad-to-AEDB
case is that a coordinate-port debug override placed the terminal at a
bump/pad center with a via directly underneath. HFSS 3D Layout can show a port
label and include it in `port_list`, while the reference terminal is not
exportable for network data.

For this case:

- Do not switch to coordinate ports as the normal repair. Rebuild with
  `edb_polygon_edge` first and select a local signal launch edge plus nearby
  solid reference edge/primitive.
- If an explicit coordinate-port debug override is approved, keep the positive
  terminal on the signal pad/trace and set `negative_x`/`negative_y` on the
  reference plane at nearby solid copper, offset from the via center by at
  least via radius plus clearance. This override must be documented and must
  still produce a non-empty Touchstone before ADS handoff.
- Run `check:port-launch` before import/solve.
- Inspect the AEDB primitives by net/layer and confirm whether signal geometry
  is path or polygon based.
- Use `edb_polygon_edge` as the first-choice method for KiCad/AEDB imports.
  If polygon primitives are not available, use `edb_path_edge`. Try coordinate
  `circuit` location ports only as an explicit override/debug path and require
  actual non-empty Touchstone export before ADS handoff.
- If Gap polygon-edge ports persist and setup/sweep are registered but export
  still reports no data, check for stale `.asol_priv` or `*.semaphore` locks
  and leftover harness non-graphical AEDT processes before switching to Wave
  ports or redesigning the geometry. Clean only case-local lock files.
- Reopen the saved project and verify `app.port_list`, Touchstone port markers,
  and frequency data lines. Passing `analyze_setup()` is not enough.
- Enable HFSS 3D Layout export-on-completion when available, but treat it as a
  supplement to explicit export and file validation. It does not fix invalid
  ports by itself.
- Run native AEDT `ExportNetworkData` as an independent check when PyAEDT
  export fails. If both fail after a truthy solve, classify the result as
  `invalid_or_non_exportable_hfss3dlayout_ports` or blocked Touchstone export.
- Keep source AEDB and work AEDB/AEDT base names distinct. Never overwrite a
  work project with the same base path as the source AEDB.
- Pass the intended AEDT version explicitly to every import, solve, and export
  command. Reject a solve/export summary from a different AEDT major release
  unless the engineer explicitly accepts compatibility risk.
- Do not synthesize or substitute S-parameters to unblock ADS. The normal
  handoff requires a verified HFSS or measurement Touchstone. If Touchstone
  export fails, keep repairing the port method, AEDB/database build, target
  AEDT version, or candidate layout until export succeeds, or record a blocker.
