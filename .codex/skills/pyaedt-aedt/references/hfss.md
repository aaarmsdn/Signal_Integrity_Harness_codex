# HFSS PyAEDT guide

Use this reference for HFSS 3D electromagnetic automation with `ansys.aedt.core.hfss.Hfss`.

## Intent mapping

- Antenna, waveguide, connector, cavity, package EM, field solve: use `Hfss`.
- PCB layout or EDB-driven layout solve: prefer `Hfss3dLayout`, not `Hfss`.
- Port/S-parameter extraction from 3D geometry: use `Hfss` with modal or terminal solution type.
- Fast SI extraction from layout: consider `Hfss3dLayout` or Q3D depending on the user's model source.
- Simple microstrip S21 extraction from dimensions: prefer the bundled `scripts/hfss_microstrip_s21.py` automation script before hand-writing a new script.

## Bundled microstrip S21 automation

For requests like "HFSS로 FR4 microstrip line S21 data를 얻어줘", run:

```powershell
python skills/pyaedt-aedt/scripts/hfss_microstrip_s21.py `
  --line-width-mm 5 `
  --copper-thickness 1oz `
  --substrate-height-mm 3 `
  --line-length-mm 50 `
  --start-ghz 0.1 `
  --stop-ghz 10 `
  --points 201 `
  --run-solve
```

Ask for or infer missing values before execution:

- `line_length_mm`
- frequency sweep start/stop/points
- AEDT version if multiple versions may be installed
- graphical vs non-graphical execution
- output directory

The script creates a timestamped project and writes a JSON summary, Touchstone file, and S21 CSV under `outputs/hfss_microstrip_s21`.

## Session pattern

```python
from ansys.aedt.core import Hfss

hfss = Hfss(
    project="project.aedt",
    design="HFSSDesign1",
    solution_type="Modal",
    version="2026.1",
    non_graphical=False,
    new_desktop=False,
    close_on_exit=False,
)
```

Use `solution_type="Modal"` for many antenna/waveguide problems. Use terminal-style setups when the user needs terminal ports and terminal S-parameters.

## Common object graph

- `hfss.modeler`: create and modify solids, sheets, coordinate systems, regions.
- `hfss.materials`: create and assign materials.
- `hfss.mesh`: mesh operations.
- `hfss.post`: reports, field plots, solution data, image/table export.
- `hfss.variable_manager` and `hfss["name"]`: project/design variables.
- `hfss.setups`: existing setup objects.

Search the inventory for exact method names before using less common APIs:

```powershell
rg "ansys.aedt.core.hfss.Hfss.*wave|ansys.aedt.core.hfss.Hfss.*port|ansys.aedt.core.hfss.Hfss.*sweep" pyaedt_api_inventory.csv
rg "Modeler3D.*create_box|Modeler3D.*create_cylinder|Modeler3D.*create_region" pyaedt_api_inventory.csv
```

## Geometry pattern

Prefer variables for dimensions and units:

```python
hfss["sub_x"] = "50mm"
hfss["sub_y"] = "40mm"
hfss["sub_h"] = "1.6mm"

substrate = hfss.modeler.create_box(
    origin=["-sub_x/2", "-sub_y/2", "0mm"],
    sizes=["sub_x", "sub_y", "sub_h"],
    name="substrate",
    material="FR4_epoxy",
)
```

Modeling guidance:

- Use returned object handles when possible.
- Name every important object deterministically.
- Keep units explicit in strings.
- Avoid hard-coded default materials; assign materials intentionally.
- Create air regions or radiation boundaries explicitly for open-boundary radiation problems.

## Boundaries and excitations

Typical HFSS boundary/excitation categories:

- Wave ports for waveguide/coax/connector cross sections.
- Lumped ports for local feed gaps and terminal approximations.
- Radiation or PML/open region boundaries for antennas and scattering.
- Perfect E/H, impedance, finite conductivity, symmetry, master/slave or periodic boundaries for specialized models.

Pattern:

```python
# Pseudocode: verify exact method signature in inventory/docs first.
hfss.assign_radiation_boundary_to_objects(["air_region"])
hfss.lumped_port(
    assignment="feed_sheet",
    reference="ground",
    impedance=50,
    name="P1",
)
```

Do not invent port signatures. Search the inventory and official docs for the exact method because PyAEDT port helpers differ by version and solution type.

## Setups and sweeps

Basic pattern:

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

Setup guidance:

- State the adaptive frequency.
- State convergence criteria if the result quality matters.
- Use interpolating/discrete/fast sweep intentionally; do not default silently for signoff work.
- Gate actual solving behind a user-controlled flag.

```python
if run_solve:
    hfss.analyze_setup("Setup1")
```

## Reports and exports

Common outputs:

- S-parameters as Touchstone.
- Rectangular plots for `dB(S(1,1))`, insertion loss, impedance, gain.
- Far-field reports for antennas.
- Field plots and images.
- Convergence and mesh statistics.

Pattern:

```python
if export_touchstone:
    hfss.export_touchstone(setup="Setup1", sweep="Sweep1", output_file="results.s2p")
```

Before writing exports:

- Confirm output directory.
- Avoid overwriting unless the user asked.
- Include setup/sweep names in filenames for traceability.

## Common failure points

- AEDT version mismatch with installed desktop.
- Project lock files from a previous AEDT session.
- Port assignment to the wrong sheet/object or wrong integration line.
- Missing air region for radiation problems.
- Ambiguous units when numeric values are passed without strings.
- Running solves unintentionally during script generation.
