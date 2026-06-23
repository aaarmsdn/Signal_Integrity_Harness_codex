# PyAEDT MCP adapter guide

Use this reference when designing or implementing an MCP server that wraps PyAEDT.

## Design principle

Do not expose PyAEDT one method at a time. The stable documentation inventory contains thousands of documented methods and properties. A method-per-tool MCP server will be noisy, brittle, and difficult for LLMs to select from.

Expose a small task-oriented surface and keep PyAEDT method resolution inside the adapter.

## Recommended tool surface

### `launch_aedt`

Purpose: create or attach to an AEDT desktop session.

Inputs:

- `version`
- `non_graphical`
- `new_desktop`
- `machine`
- `port`
- `aedt_process_id`

Returns:

- `session_id`
- `version`
- `desktop_state`
- `warnings`

### `open_project`

Purpose: open or create a project.

Inputs:

- `session_id`
- `project_path`
- `create_if_missing`
- `readonly`

Returns:

- `project_id`
- `project_name`
- `active_designs`
- `warnings`

### `create_design`

Purpose: create or select a solver design.

Inputs:

- `session_id`
- `project_id`
- `product`
- `design_name`
- `solution_type`

Supported `product` values:

- `hfss`
- `hfss3dlayout`
- `q3d`
- `q2d`
- `maxwell2d`
- `maxwell3d`
- `icepak`
- `mechanical`
- `circuit`
- `emit`
- `rmxprt`
- `twinbuilder`

Returns:

- `design_id`
- `app_class`
- `solution_type`
- `warnings`

### `modeler_action`

Purpose: create, modify, query, import, or export geometry/schematic/layout objects.

Inputs:

- `session_id`
- `design_id`
- `action`
- `arguments`

Common actions:

- `create_box`
- `create_cylinder`
- `create_rectangle`
- `create_polyline`
- `create_region`
- `subtract`
- `unite`
- `move`
- `duplicate`
- `import_cad`
- `export_model`
- `list_objects`

Returns:

- `objects`
- `method`
- `warnings`

### `assign_material`

Purpose: create or assign materials.

Inputs:

- `session_id`
- `design_id`
- `objects`
- `material`
- `properties`

Returns:

- `assigned`
- `created_materials`
- `method`
- `warnings`

### `assign_boundary`

Purpose: assign solver-specific boundaries, ports, excitations, loads, or conductor roles.

Inputs:

- `session_id`
- `design_id`
- `boundary_type`
- `assignment`
- `reference`
- `properties`

Returns:

- `boundary_name`
- `method`
- `warnings`

### `create_setup`

Purpose: create setup and sweep definitions.

Inputs:

- `session_id`
- `design_id`
- `setup_name`
- `setup_type`
- `properties`
- `sweeps`

Returns:

- `setup_name`
- `sweeps`
- `method`
- `warnings`

### `run_analysis`

Purpose: run a setup or all setups.

Inputs:

- `session_id`
- `design_id`
- `setup_name`
- `blocking`
- `confirmation_token`

Returns:

- `status`
- `started_at`
- `ended_at`
- `logs`
- `warnings`

Require confirmation for this tool.

### `export_results`

Purpose: export Touchstone, matrices, fields, reports, images, tables, or solution data.

Inputs:

- `session_id`
- `design_id`
- `export_type`
- `setup`
- `sweep`
- `expressions`
- `output_path`
- `overwrite`

Returns:

- `files`
- `method`
- `warnings`

Require confirmation before overwrite.

### `close_aedt`

Purpose: release resources.

Inputs:

- `session_id`
- `save_projects`
- `close_projects`
- `close_desktop`

Returns:

- `status`
- `warnings`

Require confirmation for closing projects or desktop.

## Adapter architecture

Use this structure:

```text
mcp_server/
  server.py
  pyaedt_adapter/
    sessions.py
    products.py
    actions_modeler.py
    actions_boundary.py
    actions_setup.py
    actions_export.py
    schemas.py
    inventory.py
```

Responsibilities:

- `sessions.py`: AEDT desktop lifecycle and session registry.
- `products.py`: product-to-class mapping and design creation.
- `actions_modeler.py`: modeler operations.
- `actions_boundary.py`: ports, excitations, conductors, thermal loads.
- `actions_setup.py`: setup, sweep, and solve operations.
- `actions_export.py`: reports and file exports.
- `schemas.py`: strict Pydantic schemas for all tool inputs.
- `inventory.py`: lookup table from normalized action names to PyAEDT qualified methods.

## Session registry

Keep live PyAEDT objects server-side:

```python
sessions = {
    "session_id": {
        "desktop": desktop,
        "projects": {},
        "designs": {},
    }
}
```

Never return raw PyAEDT objects over MCP. Return stable ids, object names, file paths, and structured metadata.

## Method dispatch

Prefer explicit dispatch tables over arbitrary `getattr`:

```python
MODELER_ACTIONS = {
    "create_box": lambda app, args: app.modeler.create_box(**args),
    "create_cylinder": lambda app, args: app.modeler.create_cylinder(**args),
}
```

Avoid unconstrained method execution:

```python
# Do not allow this from user-controlled input.
getattr(app, method_name)(**arguments)
```

If generic dispatch is necessary, restrict it to allowlisted qualified names from `pyaedt_api_inventory.csv`.

## Safety rules

Require explicit confirmation for:

- Running solves.
- Closing AEDT or projects.
- Deleting objects, designs, setups, or projects.
- Overwriting files.
- Removing lock files.
- Changing global AEDT settings.
- Running scripts supplied by the user inside AEDT.

Validate:

- Paths are inside approved workspaces unless explicitly allowed.
- File extensions match export type.
- Product/design compatibility.
- Setup and sweep names exist before solve/export.
- Object names exist before assignment.

## Return shape

Every MCP tool should return:

```json
{
  "status": "ok",
  "message": "Created setup Setup1.",
  "method": "ansys.aedt.core.hfss.Hfss.create_setup",
  "objects": [],
  "files": [],
  "warnings": []
}
```

Use `status="needs_confirmation"` when the request is valid but unsafe to execute without approval.

## LLM prompt contract

The MCP server should make the LLM responsible for intent and the adapter responsible for safety.

Good LLM behavior:

- Choose product and operation domain.
- Search or cite the PyAEDT method used.
- Ask for missing electrical intent.
- Generate structured tool inputs.

Adapter behavior:

- Validate schema.
- Check object existence.
- Prevent unsafe execution.
- Call PyAEDT.
- Return structured results.

## Minimal first implementation

Implement in this order:

1. `launch_aedt`
2. `open_project`
3. `create_design`
4. `modeler_action` with only `create_box`, `create_cylinder`, `create_rectangle`, `unite`, `subtract`, `list_objects`
5. `assign_material`
6. `create_setup`
7. `export_results`

Add `assign_boundary` and `run_analysis` after the read/create/export path is stable.

## Bundled first MCP server

This skill includes a first concrete MCP wrapper:

```text
skills/pyaedt-aedt/mcp_server/pyaedt_mcp_server.py
```

It exposes:

```text
check_pyaedt_environment
run_hfss_microstrip_s21
```

This tool delegates to:

```text
skills/pyaedt-aedt/scripts/hfss_microstrip_s21.py
```

Example MCP server command:

```powershell
python <repo>\skills\pyaedt-aedt\mcp_server\pyaedt_mcp_server.py
```

Example tool arguments:

```json
{
  "line_width_mm": 5,
  "copper_thickness": "1oz",
  "substrate_height_mm": 3,
  "line_length_mm": 50,
  "start_ghz": 0.1,
  "stop_ghz": 10,
  "points": 201,
  "run_solve": true,
  "output_dir": "outputs/hfss_microstrip_s21"
}
```

If the official `mcp` Python package is installed, the server runs as a FastMCP server. Otherwise it falls back to a minimal line-oriented JSON-RPC implementation for local experimentation.

Recommended first call after Codex restart:

```text
check_pyaedt_environment
```

Only call `run_hfss_microstrip_s21` with `run_solve=true` after the environment check reports that `ansys.aedt.core` imports successfully.
