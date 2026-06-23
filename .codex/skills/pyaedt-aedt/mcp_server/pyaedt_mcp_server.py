#!/usr/bin/env python3
"""Minimal MCP wrapper for PyAEDT automation scripts.

Primary tool:
    run_hfss_microstrip_s21

The tool delegates to ../scripts/hfss_microstrip_s21.py and returns the JSON
summary produced by that script. If the official `mcp` Python package is
installed, this file runs as a FastMCP server. Otherwise it provides a small
line-oriented JSON-RPC fallback for local experimentation.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = SKILL_ROOT.parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "hfss_microstrip_s21.py"


def _append_flag(args: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        if value:
            args.append(flag)
        return
    args.extend([flag, str(value)])


def run_hfss_microstrip_s21_impl(
    output_dir: str = "outputs/hfss_microstrip_s21",
    project_prefix: str = "microstrip_s21",
    design: str = "Microstrip_S21",
    version: str | None = None,
    non_graphical: bool = False,
    new_desktop: bool = False,
    remove_lock: bool = False,
    close_desktop: bool = False,
    line_length_mm: float = 50.0,
    line_width_mm: float = 5.0,
    substrate_height_mm: float = 3.0,
    substrate_width_mm: float = 30.0,
    copper_thickness: str = "1oz",
    substrate_material: str = "FR4_epoxy",
    start_ghz: float = 0.1,
    stop_ghz: float = 10.0,
    points: int = 201,
    adaptive_ghz: float = 5.0,
    max_passes: int = 8,
    impedance: float = 50.0,
    setup: str = "Setup1",
    sweep: str = "Sweep1",
    run_solve: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run the HFSS microstrip S21 script and return a structured result."""

    output_path = Path(output_dir)
    if not output_path.is_absolute():
        output_path = WORKSPACE_ROOT / output_path

    cmd = [sys.executable, str(SCRIPT_PATH)]
    _append_flag(cmd, "--output-dir", str(output_path))
    _append_flag(cmd, "--project-prefix", project_prefix)
    _append_flag(cmd, "--design", design)
    _append_flag(cmd, "--version", version)
    _append_flag(cmd, "--non-graphical", non_graphical)
    _append_flag(cmd, "--new-desktop", new_desktop)
    _append_flag(cmd, "--remove-lock", remove_lock)
    _append_flag(cmd, "--close-desktop", close_desktop)
    _append_flag(cmd, "--line-length-mm", line_length_mm)
    _append_flag(cmd, "--line-width-mm", line_width_mm)
    _append_flag(cmd, "--substrate-height-mm", substrate_height_mm)
    _append_flag(cmd, "--substrate-width-mm", substrate_width_mm)
    _append_flag(cmd, "--copper-thickness", copper_thickness)
    _append_flag(cmd, "--substrate-material", substrate_material)
    _append_flag(cmd, "--start-ghz", start_ghz)
    _append_flag(cmd, "--stop-ghz", stop_ghz)
    _append_flag(cmd, "--points", points)
    _append_flag(cmd, "--adaptive-ghz", adaptive_ghz)
    _append_flag(cmd, "--max-passes", max_passes)
    _append_flag(cmd, "--impedance", impedance)
    _append_flag(cmd, "--setup", setup)
    _append_flag(cmd, "--sweep", sweep)
    _append_flag(cmd, "--run-solve", run_solve)

    completed = subprocess.run(
        cmd,
        cwd=str(WORKSPACE_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    parsed_stdout: Any = None
    stdout = completed.stdout.strip()
    if stdout:
        try:
            parsed_stdout = json.loads(stdout[stdout.find("{") : stdout.rfind("}") + 1])
        except Exception:
            parsed_stdout = stdout

    result = {
        "status": "ok" if completed.returncode == 0 else "error",
        "returncode": completed.returncode,
        "command": cmd,
        "summary": parsed_stdout,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    return result


def check_pyaedt_environment_impl() -> dict[str, Any]:
    """Return Python, PyAEDT, and basic AEDT import environment information."""

    result: dict[str, Any] = {
        "status": "ok",
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "workspace_root": str(WORKSPACE_ROOT),
        "skill_root": str(SKILL_ROOT),
        "pyaedt_available": False,
        "pyaedt_version": None,
        "ansys_aedt_core_path": None,
        "warnings": [],
    }

    try:
        import ansys.aedt.core as aedt_core

        result["pyaedt_available"] = True
        result["pyaedt_version"] = getattr(aedt_core, "__version__", None)
        result["ansys_aedt_core_path"] = str(Path(aedt_core.__file__).resolve())
    except Exception as exc:
        result["status"] = "error"
        result["warnings"].append(f"Failed to import ansys.aedt.core: {exc!r}")

    return result


TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "output_dir": {"type": "string", "default": "outputs/hfss_microstrip_s21"},
        "project_prefix": {"type": "string", "default": "microstrip_s21"},
        "design": {"type": "string", "default": "Microstrip_S21"},
        "version": {"type": ["string", "null"], "default": None},
        "non_graphical": {"type": "boolean", "default": False},
        "new_desktop": {"type": "boolean", "default": False},
        "remove_lock": {"type": "boolean", "default": False},
        "close_desktop": {"type": "boolean", "default": False},
        "line_length_mm": {"type": "number", "default": 50.0},
        "line_width_mm": {"type": "number", "default": 5.0},
        "substrate_height_mm": {"type": "number", "default": 3.0},
        "substrate_width_mm": {"type": "number", "default": 30.0},
        "copper_thickness": {"type": "string", "default": "1oz"},
        "substrate_material": {"type": "string", "default": "FR4_epoxy"},
        "start_ghz": {"type": "number", "default": 0.1},
        "stop_ghz": {"type": "number", "default": 10.0},
        "points": {"type": "integer", "default": 201},
        "adaptive_ghz": {"type": "number", "default": 5.0},
        "max_passes": {"type": "integer", "default": 8},
        "impedance": {"type": "number", "default": 50.0},
        "setup": {"type": "string", "default": "Setup1"},
        "sweep": {"type": "string", "default": "Sweep1"},
        "run_solve": {
            "type": "boolean",
            "default": False,
            "description": "Set true to run HFSS solve and export S21 data. False only builds/saves project.",
        },
        "timeout_seconds": {"type": ["integer", "null"], "default": None},
    },
}

CHECK_ENV_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}


def run_fastmcp() -> bool:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        return False

    mcp = FastMCP("pyaedt-aedt")

    @mcp.tool()
    def check_pyaedt_environment() -> str:
        """Check whether the MCP Python environment can import PyAEDT."""

        return json.dumps(check_pyaedt_environment_impl(), indent=2)

    @mcp.tool()
    def run_hfss_microstrip_s21(
        output_dir: str = "outputs/hfss_microstrip_s21",
        project_prefix: str = "microstrip_s21",
        design: str = "Microstrip_S21",
        version: str | None = None,
        non_graphical: bool = False,
        new_desktop: bool = False,
        remove_lock: bool = False,
        close_desktop: bool = False,
        line_length_mm: float = 50.0,
        line_width_mm: float = 5.0,
        substrate_height_mm: float = 3.0,
        substrate_width_mm: float = 30.0,
        copper_thickness: str = "1oz",
        substrate_material: str = "FR4_epoxy",
        start_ghz: float = 0.1,
        stop_ghz: float = 10.0,
        points: int = 201,
        adaptive_ghz: float = 5.0,
        max_passes: int = 8,
        impedance: float = 50.0,
        setup: str = "Setup1",
        sweep: str = "Sweep1",
        run_solve: bool = False,
        timeout_seconds: int | None = None,
    ) -> str:
        """Create an HFSS microstrip line model and optionally solve/export S21."""

        result = run_hfss_microstrip_s21_impl(
            output_dir=output_dir,
            project_prefix=project_prefix,
            design=design,
            version=version,
            non_graphical=non_graphical,
            new_desktop=new_desktop,
            remove_lock=remove_lock,
            close_desktop=close_desktop,
            line_length_mm=line_length_mm,
            line_width_mm=line_width_mm,
            substrate_height_mm=substrate_height_mm,
            substrate_width_mm=substrate_width_mm,
            copper_thickness=copper_thickness,
            substrate_material=substrate_material,
            start_ghz=start_ghz,
            stop_ghz=stop_ghz,
            points=points,
            adaptive_ghz=adaptive_ghz,
            max_passes=max_passes,
            impedance=impedance,
            setup=setup,
            sweep=sweep,
            run_solve=run_solve,
            timeout_seconds=timeout_seconds,
        )
        return json.dumps(result, indent=2)

    mcp.run()
    return True


def write_json_rpc(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def handle_json_rpc(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pyaedt-aedt", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "check_pyaedt_environment",
                        "description": "Check Python and PyAEDT availability for the PyAEDT MCP server.",
                        "inputSchema": CHECK_ENV_SCHEMA,
                    },
                    {
                        "name": "run_hfss_microstrip_s21",
                        "description": "Create an HFSS microstrip line model and optionally solve/export S21 data.",
                        "inputSchema": TOOL_SCHEMA,
                    }
                ]
            },
        }

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "check_pyaedt_environment":
            result = check_pyaedt_environment_impl()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": result.get("status") != "ok",
                },
            }
        if name != "run_hfss_microstrip_s21":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        try:
            result = run_hfss_microstrip_s21_impl(**arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": result.get("status") != "ok",
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": repr(exc)}],
                    "isError": True,
                },
            }

    if request_id is None:
        return None

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def run_json_rpc_fallback() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_json_rpc(request)
            if response is not None:
                write_json_rpc(response)
        except Exception as exc:
            write_json_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": repr(exc)},
                }
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fallback-jsonrpc", action="store_true")
    args = parser.parse_args()

    if not args.fallback_jsonrpc and run_fastmcp():
        return 0
    return run_json_rpc_fallback()


if __name__ == "__main__":
    raise SystemExit(main())
