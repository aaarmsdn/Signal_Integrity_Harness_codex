# Circuit and Nexxim PyAEDT guide

Use this reference for schematic-level Circuit/Nexxim automation with `ansys.aedt.core.circuit.Circuit`.

## Intent mapping

- Schematic simulation, sources, lumped components, S-parameter blocks, transient/AC analyses: use `Circuit`.
- Full-wave 3D EM: use `Hfss`.
- 2D/3D RLGC extraction: use `Q2d` or `Q3d`.
- System-level dynamic models: consider `TwinBuilder`.

## Session pattern

```python
from ansys.aedt.core import Circuit

circuit = Circuit(
    project="project.aedt",
    design="CircuitDesign1",
    version="2026.1",
    non_graphical=False,
    new_desktop=False,
    close_on_exit=False,
)
```

## Common object graph

- `circuit.modeler.schematic`: place and connect schematic components.
- `circuit.post`: reports and solution data.
- `circuit.variable_manager` and `circuit["name"]`: design variables.
- App-level Circuit methods: setup creation, source management, Touchstone/import/export helpers.

Search before using exact schematic APIs:

```powershell
rg "ansys.aedt.core.circuit.Circuit.*touchstone|ansys.aedt.core.circuit.Circuit.*setup|ansys.aedt.core.circuit.Circuit.*source" pyaedt_api_inventory.csv
rg "Schematic.*create|Schematic.*connect|CircuitComponents" pyaedt_api_inventory.csv
```

## Schematic workflow

1. Create or open a Circuit design.
2. Define variables for component values.
3. Place components and ports with deterministic names.
4. Connect pins with wires or page ports.
5. Create setup and sweep.
6. Analyze only after explicit user confirmation.
7. Export plots, Touchstone, tables, or solution data.

Skeleton:

```python
from ansys.aedt.core import Circuit

circuit = Circuit(project="network.aedt", design="filter", version="2026.1")
circuit["r_src"] = "50ohm"
circuit["c_shunt"] = "1pF"

schematic = circuit.modeler.schematic

# Place components using schematic/component APIs after checking exact names.
# Example intent:
# source = schematic.create_voltage_source(...)
# resistor = schematic.create_resistor(...)
# capacitor = schematic.create_capacitor(...)
# schematic.connect_components_in_series([...])

setup = circuit.create_setup(name="Setup1")

if run_solve:
    circuit.analyze_setup("Setup1")
```

Do not invent component placement method signatures. PyAEDT has several helper layers for schematic components, and signatures vary by component type.

## Touchstone and network workflows

Common tasks:

- Import an `.sNp` file as an N-port block.
- Create terminations and excitations.
- Cascade networks.
- Plot `S`, `Y`, `Z`, gain, impedance, or time-domain responses.
- Export simulated network data.

Guidance:

- Preserve port order from the Touchstone file.
- Name imported blocks by filename and role.
- State reference impedance assumptions.
- Check whether the user wants single-ended, differential, or mixed-mode outputs.

## Setups and sweeps

Circuit setup choices depend on analysis type:

- Linear frequency sweep for S-parameter networks.
- Transient for time-domain waveforms.
- DC operating point for bias networks.
- AC analysis for small-signal circuits.

When the user gives only a frequency range, default to script generation with a linear frequency sweep and ask before running.

## Reports and exports

Common outputs:

- Rectangular plots for `dB(S(...))`, impedance, voltage, current, gain.
- Touchstone export.
- CSV tables.
- Solution data objects for downstream Python plotting.

Export guidance:

- Include analysis type and sweep range in filenames.
- Keep raw AEDT report data separate from processed plots.
- For Touchstone, confirm port count and ordering.

## Common failure points

- Component names differ from schematic instance names.
- Pin ordering is wrong when wiring components programmatically.
- Imported Touchstone port order is not documented.
- Units are omitted for component values.
- A transient source is used with a frequency-domain setup or vice versa.

