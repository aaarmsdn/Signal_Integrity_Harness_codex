---
name: pyaedt-aedt
description: Work with Ansys Electronics Desktop automation through PyAEDT. Use when Codex needs to create, inspect, or modify AEDT projects and designs; automate HFSS, HFSS 3D Layout, Q3D/Q2D, Maxwell, Icepak, Mechanical, Circuit/Nexxim, EMIT, RMxprt, or Twin Builder workflows; generate PyAEDT scripts; map user intent to PyAEDT classes, methods, properties, or solver workflows; or design an MCP adapter for PyAEDT.
---

# PyAEDT AEDT Automation

Use this skill to turn user intent into safe, maintainable PyAEDT automation.

PyAEDT is not a flat function library. Treat it as an object graph rooted in an AEDT app session:

```python
from ansys.aedt.core import Hfss

hfss = Hfss(
    project="project.aedt",
    design="Design1",
    version="2026.1",
    non_graphical=False,
    new_desktop=False,
    close_on_exit=False,
)
```

## Required assumptions

- PyAEDT requires a licensed local or remote Ansys Electronics Desktop installation.
- AEDT launch, solve, export, and project mutation can be slow or stateful.
- Prefer generating scripts over directly running PyAEDT unless the user explicitly asks to execute automation.
- Require explicit user confirmation before destructive operations such as deleting projects, deleting designs, overwriting exports, closing AEDT, releasing desktop sessions, removing lock files, or running long solves.
- Do not expose thousands of PyAEDT methods as individual MCP tools. Use coarse-grained tools backed by retrieval over the API inventory.

## Harness Runtime Hints

For this SI/PI harness, run AEDT automation through
`sipi_harness/scripts/run_aedt_python.mjs`. Assume `AEDT_PYTHON` and
`PYAEDT_PYTHON` are unset on a fresh machine. The selected Python must import
both `ansys.aedt.core` and `pyedb`.

The wrapper must prefer installed AEDT CPython runtimes under
`C:\Program Files\ANSYS Inc\v*`, then optional explicit
`AEDT_PYTHON`/`PYAEDT_PYTHON` overrides, then common user Python environments.
Do not assume another engineer has a personal `aedt_env`.

Typical Windows AEDT 2025 R1 candidates:

```powershell
$env:AEDT_PYTHON='C:\Program Files\ANSYS Inc\v251\AnsysEM\commonfiles\CPython\3_10\winx64\Release\python\python.exe'
# Some installs use:
$env:AEDT_PYTHON='C:\Program Files\ANSYS Inc\v251\AnsysEM\common\commonfiles\CPython\3_10\winx64\python\python.exe'
```

If those paths differ on the machine, search under `C:\Program Files\ANSYS Inc`
or use a validated Python with PyAEDT and PyEDB installed. Always pass the
intended AEDT version, for example `--version 2025.1`, and reject summaries
created by a different AEDT major release unless the engineer approves the
compatibility risk.

If the selected Python does not import `ansys.aedt.core` and `pyedb`, stop before
HFSS automation and direct the engineer to the official PyAEDT installation
guide:

```text
https://aedt.docs.pyansys.com/version/stable/Getting_started/Installation.html
```

Only install packages after the engineer approves the target Python:

```powershell
python -m pip install -U pyaedt pyedb
# or, from sipi_harness:
npm run setup:aedt-python
```

## API inventory

Use the generated inventory before guessing method names:

```text
../../pyaedt_api_inventory.csv
../../pyaedt_api_inventory.md
```

The CSV columns are:

```text
area,type,owner,member,qualified_name,url
```

Search patterns:

```powershell
rg "create_box|wave_port|assign_radiation|export_touchstone" pyaedt_api_inventory.csv
rg "SetupHFSS|SweepHFSS|Modeler3D|BoundaryObject" pyaedt_api_inventory.csv
rg "area-name-or-solver-name" pyaedt_api_inventory.csv
```

Official docs:

```text
https://aedt.docs.pyansys.com/version/stable/API/index.html
https://aedt.docs.pyansys.com/version/stable/User_guide/index.html
https://github.com/ansys/pyaedt
```

## Solver references

Load only the reference needed for the current task:

- `references/application-solvers.md`: exhaustive methods/properties for Desktop and main app classes shown in `API/Application.html`.
- `references/hfss.md`: HFSS 3D modeler, ports, boundaries, setups, sweeps, Touchstone/report exports.
- `references/q3d.md`: Q3D/Q2D extraction, nets, sources/sinks, matrix reduction, RLGC/capacitance workflows.
- `references/circuit.md`: Circuit/Nexxim schematic automation, components, ports, sources, setups, reports.
- `references/mcp-adapter.md`: Design a small MCP wrapper around PyAEDT without exposing every method.

## Executable automation scripts

Use bundled scripts when the user asks Codex to run AEDT automatically rather than only generate PyAEDT code:

- `scripts/hfss_microstrip_s21.py`: create an HFSS microstrip line project, assign microstrip wave ports, create setup/sweep, optionally solve, export Touchstone, and extract S21 CSV.
- `mcp_server/pyaedt_mcp_server.py`: MCP server exposing `check_pyaedt_environment` and `run_hfss_microstrip_s21`, which delegates to the script above.

For solve-capable scripts:

- Call `check_pyaedt_environment` first when available.
- Default to creating a new timestamped project under `outputs/` to avoid overwriting user projects.
- Pass `--run-solve` only when the user explicitly asks to execute the solve or confirms execution.
- Report the generated `.aedt`, `.s2p`, `.csv`, and summary JSON paths.
- Keep `--close-desktop` opt-in so an existing AEDT session is not closed unexpectedly.

## Workflow

1. Identify the AEDT product.
2. Identify the operation domain.
3. Search the API inventory for likely classes and methods.
4. Write PyAEDT code that uses app-level properties before low-level AEDT COM objects.
5. Keep solver-specific code isolated from common setup/project/session code.
6. Add comments where AEDT version, license, file paths, or solve time are environment-dependent.

Product selection:

- HFSS 3D EM: `ansys.aedt.core.hfss.Hfss`
- HFSS 3D Layout: `ansys.aedt.core.hfss3dlayout.Hfss3dLayout`
- Q3D or Q2D extraction: `ansys.aedt.core.q3d.Q3d`, `ansys.aedt.core.q3d.Q2d`
- Maxwell 2D or 3D: `ansys.aedt.core.maxwell.Maxwell2d`, `ansys.aedt.core.maxwell.Maxwell3d`
- Icepak thermal: `ansys.aedt.core.icepak.Icepak`
- Mechanical in AEDT: `ansys.aedt.core.mechanical.Mechanical`
- Circuit or Nexxim: `ansys.aedt.core.circuit.Circuit`
- Maxwell Circuit: `ansys.aedt.core.maxwellcircuit.MaxwellCircuit`
- EMIT: `ansys.aedt.core.emit.Emit`
- RMxprt: `ansys.aedt.core.rmxprt.Rmxprt`
- Twin Builder: `ansys.aedt.core.twinbuilder.TwinBuilder`
- Desktop/session only: `ansys.aedt.core.desktop.Desktop`

Operation domains:

- Session/project/design: app constructors, `launch_desktop`, project open/save/archive, design insert/rename/delete.
- Geometry/modeling: `app.modeler`, 3D primitives, 2D primitives, layout modeler, circuit schematic modeler.
- Materials/stackup: `app.materials`, material manager, stackup objects.
- Boundaries/excitations: app-level boundary methods and `ansys.aedt.core.modules.boundary`.
- Mesh: `app.mesh`, mesh operation classes.
- Setup/sweep/solve: `app.create_setup`, setup classes, sweep classes, `analyze`, `analyze_setup`.
- Variables/datasets: `app.variable_manager`, app variable helpers, dataset helpers.
- Optimetrics: `app.parametrics`, `app.optimizations`.
- Postprocessing/export: `app.post`, report classes, field plots, Touchstone export, image/PDF/report export.
- File import/export: CAD import, DXF/GDS import, tables, Sherlock files, 3D model export.

## Coding patterns

Use explicit app variables for geometry and setup scripts:

```python
from ansys.aedt.core import Hfss

hfss = Hfss(project="demo.aedt", design="patch", solution_type="Modal", version="2026.1")
hfss["patch_w"] = "38mm"
hfss["patch_l"] = "29mm"

substrate = hfss.modeler.create_box(
    origin=["-25mm", "-20mm", "0mm"],
    sizes=["50mm", "40mm", "1.6mm"],
    name="substrate",
    material="FR4_epoxy",
)
```

Use app-level methods when available:

```python
setup = hfss.create_setup(name="Setup1")
hfss.create_linear_count_sweep(
    setup="Setup1",
    units="GHz",
    start_frequency=1,
    stop_frequency=10,
    num_of_freq_points=101,
    name="Sweep1",
)
```

Use object handles rather than names when the modeler returns objects, but accept names when PyAEDT docs show that a method expects names.

Keep execution guarded:

```python
if run_solve:
    hfss.analyze_setup("Setup1")
```

Close or release only when the user asked for lifecycle ownership:

```python
if close_when_done:
    hfss.release_desktop(close_projects=False, close_desktop=False)
```

## MCP adapter guidance

Create a small MCP surface and route detailed actions through a validated adapter.

Recommended MCP tools:

- `launch_aedt`: start or connect to AEDT, return a session id.
- `open_project`: open or create a project and select a design.
- `create_design`: insert/select a solver-specific design.
- `modeler_action`: create, modify, query, import, or export geometry.
- `assign_material`: apply or create material definitions.
- `assign_boundary`: assign ports, excitations, thermal loads, radiation, conductors, or solver-specific boundaries.
- `create_setup`: create setup and sweeps from a normalized schema.
- `run_analysis`: run a setup or batch job after explicit confirmation.
- `export_results`: export Touchstone, fields, reports, images, tables, or convergence data.
- `postprocess_report`: create report definitions or retrieve plotted data.
- `close_aedt`: release or close resources after explicit confirmation.

Adapter rules:

- Maintain a session registry keyed by `session_id`.
- Validate `product`, `project`, `design`, and `solution_type` before mutation.
- Validate all file paths and prevent accidental overwrite unless `overwrite=true`.
- Map high-level requests to known PyAEDT qualified names found in the inventory.
- Return structured results with `status`, `message`, `objects`, `files`, and `warnings`.
- Include the PyAEDT qualified method name used in tool output for auditability.

Do not make an MCP tool for every PyAEDT method. Use the inventory as retrieval context and implement a controlled dispatch layer.

## Response style for PyAEDT tasks

When writing code for users:

- State the target AEDT product and app class first.
- State whether the code launches AEDT, connects to an existing session, or only generates a script.
- Identify any required AEDT version, license, working directory, and expected input files.
- Separate safe script generation from actual solve execution.
- Mention the exact PyAEDT classes or methods used when relevant.

When uncertain:

- Search the inventory first.
- Prefer official docs over memory.
- If a method exists in multiple solver classes, choose the solver-specific class matching the user's product.
- If the user did not specify product, ask one concise clarification question unless there is an obvious default from context.
