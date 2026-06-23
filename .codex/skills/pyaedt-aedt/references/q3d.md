# Q3D and Q2D PyAEDT guide

Use this reference for quasi-static extraction workflows with `ansys.aedt.core.q3d.Q3d` and `ansys.aedt.core.q3d.Q2d`.

## Intent mapping

- 3D capacitance, conductance, resistance, inductance extraction from conductors: use `Q3d`.
- 2D cross-section RLGC or transmission-line extraction: use `Q2d`.
- Full-wave radiation, resonances, or far fields: use `Hfss`, not Q3D/Q2D.
- Circuit-only schematic simulation: use `Circuit`, not Q3D/Q2D.

## Session pattern

```python
from ansys.aedt.core import Q3d, Q2d

q3d = Q3d(
    project="project.aedt",
    design="Q3DDesign1",
    version="2026.1",
    non_graphical=False,
    new_desktop=False,
    close_on_exit=False,
)
```

For 2D extraction:

```python
q2d = Q2d(project="project.aedt", design="Q2DDesign1", version="2026.1")
```

## Common object graph

- `q3d.modeler` or `q2d.modeler`: conductor/dielectric geometry.
- `q3d.materials`: conductor and dielectric materials.
- `q3d.mesh`: mesh operations when needed.
- `q3d.post`: reports and matrix data.
- App-level Q3D/Q2D methods: sources, sinks, conductors, nets, matrix operations, setup/sweep creation.

Search before using exact net/source APIs:

```powershell
rg "ansys.aedt.core.q3d.Q3d.*source|ansys.aedt.core.q3d.Q3d.*sink|ansys.aedt.core.q3d.Q3d.*net" pyaedt_api_inventory.csv
rg "ansys.aedt.core.q3d.Q2d.*conductor|ansys.aedt.core.q3d.Q2d.*matrix|ansys.aedt.core.q3d.Q2d.*rlgc" pyaedt_api_inventory.csv
```

## Q3D workflow

1. Create or import 3D conductor and dielectric geometry.
2. Assign materials.
3. Assign conductor roles, nets, sources, and sinks.
4. Create extraction setup.
5. Add frequency sweep if needed.
6. Analyze only after explicit user confirmation.
7. Export capacitance, inductance, resistance, conductance, or reduced matrices.

Skeleton:

```python
from ansys.aedt.core import Q3d

q3d = Q3d(project="busbar.aedt", design="extractor", version="2026.1")
q3d["w"] = "5mm"
q3d["l"] = "50mm"
q3d["t"] = "0.5mm"

trace = q3d.modeler.create_box(
    origin=["0mm", "0mm", "0mm"],
    sizes=["l", "w", "t"],
    name="trace_p",
    material="copper",
)

# Add source/sink/net assignments here after checking exact PyAEDT methods.
setup = q3d.create_setup(name="Setup1")

if run_solve:
    q3d.analyze_setup("Setup1")
```

## Q2D workflow

1. Build or import a 2D cross section.
2. Assign signal, reference, and dielectric regions.
3. Assign conductor types and conductor names.
4. Create setup over the requested frequency range.
5. Export RLGC or impedance data.

Use Q2D when the geometry is translationally invariant and the user asks for per-unit-length line parameters.

## Matrix and net handling

Q3D/Q2D automation is often more sensitive to naming than HFSS.

Rules:

- Name conductors based on electrical role, not geometry creation order.
- Keep net names stable: `P`, `N`, `GND`, `SHIELD`, `SIG1`, etc.
- Explicitly identify reference conductors.
- For reduced matrices, document the reduction rule and retained nets.
- Do not merge nets or reduce matrices unless the user requested that electrical abstraction.

## Reports and exports

Common outputs:

- Capacitance matrix.
- Inductance matrix.
- Resistance matrix.
- Conductance matrix.
- RLGC data for Q2D.
- SPICE, Touchstone, or equivalent exported network data when supported by the workflow.

Export guidance:

- Include setup name and frequency point/range in output filenames.
- Preserve raw matrix exports before postprocessing.
- State whether matrix entries are self/mutual and whether units are normalized.

## Common failure points

- Using HFSS for a quasi-static extraction task that should be Q3D/Q2D.
- Missing reference conductor.
- Geometry bodies touching unintentionally.
- Incorrect dielectric assignment between conductors.
- Ambiguous source/sink placement.
- Matrix reduction that changes the intended circuit topology.

