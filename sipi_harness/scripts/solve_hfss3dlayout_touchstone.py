from __future__ import annotations

import argparse
import json
import os
import shutil
import copy
from pathlib import Path
from typing import Any

PYAEDT_API = "unloaded"


def load_hfss3dlayout():
    global PYAEDT_API
    try:
        from ansys.aedt.core import Hfss3dLayout

        PYAEDT_API = "ansys.aedt.core"
        return Hfss3dLayout
    except ModuleNotFoundError:
        from pyaedt import Hfss3dLayout

        PYAEDT_API = "pyaedt"
        return Hfss3dLayout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve an HFSS 3D Layout project and export Touchstone.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--design", default=None)
    parser.add_argument("--version", default="2025.1")
    parser.add_argument(
        "--expected-version",
        default=None,
        help="Optional required AEDT version. The solve exits before analysis if --version does not match.",
    )
    parser.add_argument("--setup", default="Setup_5xNyq")
    parser.add_argument("--sweep", default="Sweep_0p1_12G")
    parser.add_argument("--adaptive-ghz", type=float, default=4.0)
    parser.add_argument("--max-delta-s", type=float, default=None, help="Optional adaptive convergence target for HFSS.")
    parser.add_argument("--max-passes", type=int, default=None, help="Optional maximum adaptive passes.")
    parser.add_argument("--min-passes", type=int, default=None, help="Optional minimum adaptive passes.")
    parser.add_argument("--start-ghz", type=float, default=0.1)
    parser.add_argument("--stop-ghz", type=float, default=12.0)
    parser.add_argument("--points", type=int, default=7)
    parser.add_argument(
        "--sweep-type",
        default="Interpolating",
        choices=["Interpolating", "Fast", "Discrete"],
        help="HFSS sweep type. Fast is useful for Touchstone export smoke checks; use finer settings for compliance.",
    )
    parser.add_argument(
        "--freq-ghz",
        default=None,
        help="Optional comma-separated explicit frequency list in GHz, for example 0.1,4,12. Uses a single-point sweep list when provided.",
    )
    parser.add_argument("--touchstone", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--skip-solve", action="store_true")
    parser.add_argument("--skip-analyze", action="store_true", help="Open the project and export an existing solved sweep without running analyze.")
    parser.add_argument("--temp-dir", default=None, help="Optional temp directory for AEDT child processes.")
    parser.add_argument(
        "--keep-desktop-open",
        action="store_true",
        help="Leave the AEDT desktop session open after the run. Default closes the non-graphical session started by this script.",
    )
    return parser.parse_args()


def configure_runtime(temp_dir: str | None = None) -> None:
    if temp_dir:
        path = Path(temp_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        os.environ["TEMP"] = str(path)
        os.environ["TMP"] = str(path)
    try:
        from ansys.aedt.core.generic.settings import settings as pyaedt_settings

        pyaedt_settings.enable_global_log_file = True
        pyaedt_settings.enable_local_log_file = False
        if temp_dir:
            temp_path = Path(temp_dir).resolve()
            pyaedt_settings.global_log_file_name = str(temp_path / "pyaedt_solve.log")
            pyaedt_settings.aedt_log_file = str(temp_path / "aedt_solve.log")
    except Exception:
        pass


def _touchstone_valid(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _flatten_attempt_text(attempts: list[dict[str, Any]]) -> str:
    return "\n".join(str(value) for attempt in attempts for value in attempt.values())


def classify_export_failure(summary: dict[str, Any]) -> None:
    if summary.get("touchstone_exists") and int(summary.get("touchstone_size") or 0) > 0:
        summary["status"] = "touchstone_exported"
        return

    attempts = summary.get("export_attempts")
    attempt_text = _flatten_attempt_text(attempts if isinstance(attempts, list) else [])
    analyze_true = summary.get("analyze_result") is True or summary.get("sweep_analyze_result") is True
    has_ports = int(summary.get("port_count") or 0) > 0
    lower_text = attempt_text.lower()

    if has_ports and analyze_true and (
        "getallportslist" in lower_text
        or "solution data is not available" in lower_text
        or "exportnetworkdata" in lower_text
        or "nonetype" in lower_text
    ):
        summary["status"] = "blocked_no_exportable_touchstone"
        summary["failure_class"] = "invalid_or_non_exportable_hfss3dlayout_ports"
        summary["recommended_actions"] = [
            "Do not treat analyze_result=true as a valid EM result.",
            "Reopen the project in the target AEDT version and verify that the design has exportable boundary-module ports, not only visible GUI port labels.",
            "Inspect AEDB primitives by net/layer; if signal shapes are polygon/rectangle fragments, create AEDB polygon/primitive edge ports from explicit port-intent coordinates.",
            "Run native AEDT ExportNetworkData as an independent confirmation; if it also fails, rebuild ports or mark EM blocked.",
            "Do not hand off to ADS compliance until a non-empty Touchstone validates port count, order, and frequency range.",
        ]
    elif not has_ports:
        summary["status"] = "blocked_no_hfss3dlayout_ports"
        summary["failure_class"] = "missing_ports_before_solve"
        summary["recommended_actions"] = [
            "Stop before solving and regenerate ports from port-intent JSON.",
            "Do not force a generic design name such as PCB unless it is the imported AEDB cell.",
        ]
    elif not analyze_true and not summary.get("skip_solve"):
        summary["status"] = "blocked_solve_not_confirmed"
        summary["failure_class"] = "analysis_not_confirmed"
    else:
        summary["status"] = "blocked_touchstone_missing"
        summary["failure_class"] = "touchstone_missing_unknown_export_failure"


def scan_auto_export_candidates(touchstone: Path) -> list[str]:
    candidates = []
    if touchstone.parent.exists():
        for path in sorted(touchstone.parent.glob("*.s*p")):
            if path.resolve() != touchstone.resolve() and path.stat().st_size > 0:
                candidates.append(str(path))
    return candidates


def supports_export_touchstone_preferences(version: str) -> bool:
    try:
        major_text, minor_text, *_ = str(version).split(".")
        return (int(major_text), int(minor_text)) >= (2025, 1)
    except Exception:
        return False


def _try_list(value: Any) -> list[Any]:
    try:
        return list(value)
    except Exception:
        return []


def native_setup_state(app, setup_name: str, sweep_name: str | None = None) -> dict[str, Any]:
    """Read setup/sweep state through native AEDT SolveSetups APIs.

    PyAEDT can keep a Python-side setup object even when the underlying HFSS
    3D Layout design did not register the setup. Touchstone export depends on
    the native AEDT solution tree, so this state is the authority for solve
    readiness.
    """
    state: dict[str, Any] = {}
    try:
        module = app.odesign.GetModule("SolveSetups")
        state["module"] = "ok"
    except Exception as exc:
        state["module_error"] = str(exc)
        return state
    try:
        state["setups"] = _try_list(module.GetSetups())
    except Exception as exc:
        state["get_setups_error"] = str(exc)
        state["setups"] = []
    try:
        state["sweeps"] = _try_list(module.GetSweeps(setup_name))
    except Exception as exc:
        state["get_sweeps_error"] = str(exc)
        state["sweeps"] = []
    try:
        state["all_solution_names"] = _try_list(module.GetAllSolutionNames())
    except Exception as exc:
        state["get_all_solution_names_error"] = str(exc)
        state["all_solution_names"] = []
    if sweep_name:
        state["has_setup"] = setup_name in state.get("setups", [])
        state["has_sweep"] = sweep_name in state.get("sweeps", [])
    return state


def probe_sweep_solution_data(app, solution: str, ports: list[str]) -> dict[str, Any]:
    """Probe whether a named HFSS 3D Layout solution has retrievable data.

    HFSS 3D Layout can show a sweep name in the solution selector while only
    `Last Adaptive` has data. This probe is intentionally small: one S-parameter
    expression on the first port pair is enough to prove that the requested
    `Setup : Sweep` has report/export-visible data before attempting Touchstone
    export.
    """
    probe: dict[str, Any] = {"solution": solution, "ok": False}
    if len(ports) < 2:
        probe["error"] = "Need at least two ports to probe S-parameter data."
        return probe
    expression = f"S({ports[1]},{ports[0]})"
    probe["expression"] = expression
    try:
        report = app.odesign.GetModule("ReportSetup")
        data = list(report.GetSolutionDataPerVariation("Standard", solution, [], ["Freq:=", ["All"]], [expression]))
        probe["result_type"] = "GetSolutionDataPerVariation"
        probe["object_count"] = len(data)
        probe["ok"] = len(data) > 0
        if data:
            item = data[0]
            probe["first_object_type"] = type(item).__name__
            for method_name in ["GetSweepData", "GetRealDataValues", "GetImagDataValues"]:
                try:
                    value = getattr(item, method_name)("Freq") if method_name == "GetSweepData" else getattr(item, method_name)(expression)
                    probe[method_name] = len(list(value)) if value is not None else 0
                except Exception as exc:
                    probe[f"{method_name}_error"] = str(exc)
    except Exception as exc:
        probe["error"] = str(exc)
    return probe


def analyze_setup_and_sweep(app, args: argparse.Namespace, summary: dict[str, Any]) -> None:
    """Run the adaptive setup and the requested sweep as blocking operations."""
    sweep_solution = f"{args.setup} : {args.sweep}"
    summary["analyze_result"] = bool(app.analyze_setup(args.setup, blocking=True))
    try:
        summary["sweep_analyze_result"] = bool(app.analyze_setup(sweep_solution, blocking=True))
        summary["sweep_analyze_solution"] = sweep_solution
    except Exception as exc:
        summary["sweep_analyze_warning"] = str(exc)
        try:
            app.odesign.Analyze(sweep_solution)
            summary["native_sweep_analyze_result"] = "called"
            summary["native_sweep_analyze_solution"] = sweep_solution
        except Exception as native_exc:
            summary["native_sweep_analyze_error"] = str(native_exc)


def native_sweep_props(args: argparse.Namespace) -> list[Any]:
    """Build a native HFSS 3D Layout sweep with a real frequency range row.

    HFSS 3D Layout does not reliably populate the sweep table from generic
    ``RangeStart``/``RangeEnd`` properties. Use the same template PyAEDT uses
    so the native AEDT ``Sweeps/Data`` field is set to ``LINC f1 f2 n``.
    """
    try:
        from ansys.aedt.core.generic.data_handlers import _dict2arg
        from ansys.aedt.core.modules import setup_templates

        props = copy.deepcopy(setup_templates.Sweep3DLayout)
        props.setdefault("Sweeps", {})["Variable"] = "Freq"
        props.setdefault("Sweeps", {})["Data"] = f"LINC {args.start_ghz}GHz {args.stop_ghz}GHz {args.points}"
        props["GenerateSurfaceCurrent"] = False
        props["SaveRadFieldsOnly"] = False
        props["UseQ3DForDC"] = False
        props["MaxSolutions"] = 250
        if args.sweep_type == "Discrete":
            props["FreqSweepType"] = "kDiscrete"
            props["EnforcePassivity"] = False
            props["AutoSMatOnlySolve"] = False
        else:
            # Interpolating is the most portable HFSS 3D Layout export path.
            # Treat a requested Fast smoke run as a sparse interpolating sweep
            # unless a case-specific script proves a different AEDT enum.
            props["FreqSweepType"] = "kInterpolating"
            props["EnforcePassivity"] = True
            props["AutoSMatOnlySolve"] = True
        arg = ["NAME:" + args.sweep]
        _dict2arg(props, arg)
        return arg
    except Exception:
        return [
            "NAME:" + args.sweep,
            ["NAME:Properties", "Enable:=", "true"],
            [
                "NAME:Sweeps",
                "Variable:=",
                "Freq",
                "Data:=",
                f"LINC {args.start_ghz}GHz {args.stop_ghz}GHz {args.points}",
                "OffsetF1:=",
                False,
                "Synchronize:=",
                0,
            ],
            "GenerateSurfaceCurrent:=",
            False,
            "SaveRadFieldsOnly:=",
            False,
            "SAbsError:=",
            0.005,
            "EnforcePassivity:=",
            args.sweep_type != "Discrete",
            "UseQ3DForDC:=",
            False,
            "MaxSolutions:=",
            250,
            "FreqSweepType:=",
            "kDiscrete" if args.sweep_type == "Discrete" else "kInterpolating",
        ]


def ensure_native_sweep(app, args: argparse.Namespace, summary: dict[str, Any]) -> bool:
    state = native_setup_state(app, args.setup, args.sweep)
    summary["native_setup_state_before_sweep"] = state
    if not state.get("has_setup"):
        summary["status"] = "blocked_hfss3dlayout_setup_not_registered"
        summary["failure_class"] = "hfss3dlayout_setup_missing_before_sweep"
        summary["recommended_actions"] = [
            "Create a real HFSS 3D Layout solution setup before solving.",
            "Do not continue from a Python-side PyAEDT setup object unless SolveSetups.GetSetups() includes it.",
            "Open the imported design in AEDT and confirm Analysis contains the setup if automation cannot register it.",
        ]
        return False
    module = app.odesign.GetModule("SolveSetups")
    if state.get("has_sweep"):
        # Repair the requested sweep unconditionally. A visible Sweep1 can have
        # an empty HFSS 3D Layout sweep table; then only Last Adaptive exports.
        try:
            setup_obj = app.get_setup(args.setup)
            if setup_obj and hasattr(setup_obj, "delete_sweep"):
                summary["delete_existing_sweep"] = bool(setup_obj.delete_sweep(args.sweep))
            else:
                module.DeleteSweep(args.setup, args.sweep)
                summary["delete_existing_sweep"] = "called_native"
            app.save_project()
        except Exception as exc:
            summary["delete_existing_sweep_warning"] = str(exc)
    try:
        sweep = app.create_linear_count_sweep(
            setup=args.setup,
            unit="GHz",
            start_frequency=args.start_ghz,
            stop_frequency=args.stop_ghz,
            num_of_freq_points=args.points,
            name=args.sweep,
            save_fields=False,
            save_rad_fields_only=False,
            sweep_type=args.sweep_type,
            interpolation_tol_percent=0.5,
            interpolation_max_solutions=250,
            use_q3d_for_dc=False,
        )
        summary["pyaedt_create_linear_count_sweep"] = bool(sweep)
    except Exception as exc:
        summary["pyaedt_create_linear_count_sweep_error"] = str(exc)
        try:
            module.AddSweep(args.setup, native_sweep_props(args))
            summary["native_add_sweep"] = "called_template"
        except Exception as native_exc:
            summary["native_add_sweep_error"] = str(native_exc)
            summary["status"] = "blocked_hfss3dlayout_sweep_not_registered"
            summary["failure_class"] = "hfss3dlayout_add_sweep_failed"
            return False
    updated = native_setup_state(app, args.setup, args.sweep)
    summary["native_setup_state_after_sweep"] = updated
    if not updated.get("has_sweep"):
        summary["status"] = "blocked_hfss3dlayout_sweep_not_registered"
        summary["failure_class"] = "hfss3dlayout_sweep_missing_after_add"
        return False
    try:
        app.save_project()
        summary["save_after_native_sweep"] = True
    except Exception as exc:
        summary["save_after_native_sweep_warning"] = str(exc)
    return True


def main() -> int:
    args = parse_args()
    configure_runtime(args.temp_dir)
    project = Path(args.project).resolve()
    touchstone = Path(args.touchstone).resolve()
    summary_path = Path(args.summary).resolve()
    touchstone.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    lock = Path(str(project) + ".lock")
    if lock.exists():
        lock.unlink()

    if args.expected_version and args.version != args.expected_version:
        summary = {
            "project": str(project),
            "version": args.version,
            "expected_version": args.expected_version,
            "touchstone": str(touchstone),
            "status": "blocked_aedt_version_mismatch",
            "failure_class": "aedt_version_mismatch",
            "recommended_actions": [
                "Pass the project-required AEDT version explicitly to every import, solve, and export command.",
                "Do not reuse a solved/export summary from a different AEDT major release for handoff validation.",
            ],
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 3

    Hfss3dLayout = load_hfss3dlayout()

    if PYAEDT_API == "ansys.aedt.core":
        app = Hfss3dLayout(
            project=str(project),
            design=args.design,
            version=args.version,
            non_graphical=args.non_graphical,
            new_desktop=True,
            close_on_exit=False,
        )
    else:
        app = Hfss3dLayout(
            projectname=str(project),
            designname=args.design,
            specified_version=args.version,
            non_graphical=args.non_graphical,
            new_desktop_session=True,
            close_on_exit=False,
        )
    summary: dict[str, object] = {
        "project": str(project),
        "design": app.design_name,
        "version": args.version,
        "expected_version": args.expected_version,
        "pyaedt_api": PYAEDT_API,
        "setup": args.setup,
        "sweep": args.sweep,
        "start_ghz": args.start_ghz,
        "stop_ghz": args.stop_ghz,
        "points": args.points,
        "sweep_type": args.sweep_type,
        "max_delta_s": args.max_delta_s,
        "max_passes": args.max_passes,
        "min_passes": args.min_passes,
        "freq_ghz": args.freq_ghz,
        "touchstone": str(touchstone),
        "port_count": len(app.port_list),
        "ports": list(app.port_list),
        "setup_names_before": list(getattr(app, "setup_names", [])),
    }
    try:
        if not app.port_list:
            summary["status"] = "blocked_no_hfss3dlayout_ports"
            summary["failure_class"] = "missing_ports_before_solve"
            summary["recommended_actions"] = [
                "Regenerate ports from port-intent JSON before running analysis.",
                "Reopen the imported AEDB cell without forcing a generic design name.",
            ]
            return 4
        summary["native_setup_state_initial"] = native_setup_state(app, args.setup, args.sweep)
        if not summary["native_setup_state_initial"].get("has_setup"):
            setup = app.create_setup(
                name=args.setup,
                setup_type="HFSS3DLayout",
                MeshSizeFactor=2,
                SingleFrequencyDataList__AdaptiveFrequency=f"{args.adaptive_ghz}GHz",
            )
            summary["create_setup_return_type"] = type(setup).__name__ if setup else str(setup)
            summary["setup_names_after_create"] = list(getattr(app, "setup_names", []))
            try:
                app.save_project()
                summary["save_after_setup_create"] = True
            except Exception as exc:
                summary["save_after_setup_create_warning"] = str(exc)
            summary["native_setup_state_after_create"] = native_setup_state(app, args.setup, args.sweep)
            if not summary["native_setup_state_after_create"].get("has_setup"):
                summary["status"] = "blocked_hfss3dlayout_setup_not_registered"
                summary["failure_class"] = "hfss3dlayout_setup_missing_after_create"
                summary["recommended_actions"] = [
                    "HFSS 3D Layout port import succeeded, but the solution setup did not register in native AEDT SolveSetups.",
                    "Do not run analyze/export until SolveSetups.GetSetups() includes the requested setup.",
                    "Create the setup manually in AEDT or repair the setup creation API path, then rerun solve/export.",
                ]
                return 5
        else:
            setup = app.get_setup(args.setup)
        if hasattr(setup, "props"):
            if args.max_delta_s is not None:
                setup.props["MaxDeltaS"] = args.max_delta_s
            if args.max_passes is not None:
                setup.props["MaximumPasses"] = args.max_passes
            if args.min_passes is not None:
                setup.props["MinimumPasses"] = args.min_passes
            setup.update()
        if not ensure_native_sweep(app, args, summary):
            return 6
        if supports_export_touchstone_preferences(args.version):
            try:
                app.set_export_touchstone(
                    file_format="TouchStone1.0",
                    enforce_passivity=True,
                    use_common_ground=True,
                    renormalize=True,
                    impedance=50.0,
                    touchstone_output="MA",
                    units="GHz",
                )
                auto_export_dir = touchstone.parent
                summary["auto_export_on_completion"] = bool(app.export_touchstone_on_completion(True, str(auto_export_dir)))
                summary["auto_export_dir"] = str(auto_export_dir)
            except Exception as exc:
                summary["auto_export_on_completion_error"] = str(exc)
        else:
            summary["auto_export_on_completion"] = "skipped_unsupported_aedt_version"
            summary["auto_export_on_completion_note"] = (
                "set_export_touchstone requires AEDT 2025.1 or newer; using direct export attempts instead."
            )
        if args.skip_analyze:
            summary["analyze_result"] = "skipped_existing_solution"
            summary["sweep_analyze_result"] = "skipped_existing_solution"
        elif not args.skip_solve:
            summary["native_setup_state_before_analyze"] = native_setup_state(app, args.setup, args.sweep)
            if not summary["native_setup_state_before_analyze"].get("has_setup") or not summary[
                "native_setup_state_before_analyze"
            ].get("has_sweep"):
                summary["status"] = "blocked_hfss3dlayout_setup_or_sweep_missing_before_analyze"
                summary["failure_class"] = "hfss3dlayout_setup_sweep_missing_before_analyze"
                return 7
            analyze_setup_and_sweep(app, args, summary)
            summary["native_setup_state_after_analyze"] = native_setup_state(app, args.setup, args.sweep)
            sweep_solution = f"{args.setup} : {args.sweep}"
            summary["sweep_solution_data_probe"] = probe_sweep_solution_data(app, sweep_solution, list(app.port_list))
            if not summary["sweep_solution_data_probe"].get("ok"):
                summary["status"] = "blocked_hfss3dlayout_sweep_has_no_solution_data"
                summary["failure_class"] = "hfss3dlayout_sweep_name_exists_but_no_solution_data"
                summary["recommended_actions"] = [
                    "Do not export from `Last Adaptive`; it contains only the adaptive frequency.",
                    "Re-run the requested sweep as a blocking operation and verify report-visible data for `Setup : Sweep`.",
                    "If the GUI shows only `Last Adaptive` data, repair setup/sweep solve execution before ADS handoff.",
                    "Do not hand off to ADS until the requested sweep has frequency data and a non-empty Touchstone.",
                ]
                return 8
            try:
                app.save_project()
                summary["save_after_analyze"] = True
            except Exception as exc:
                summary["save_after_analyze_warning"] = str(exc)
        else:
            summary["analyze_result"] = "skipped"
            summary["exported"] = "skipped"
            summary["export_attempts"] = []
            summary["touchstone_exists"] = touchstone.exists()
            summary["touchstone_size"] = touchstone.stat().st_size if touchstone.exists() else 0
            classify_export_failure(summary)
            app.save_project()
            return 0 if _touchstone_valid(touchstone) else 2
        attempts = []
        exported = False
        for variation in ["", "Nominal"]:
            for solution in [f"{args.setup}:{args.sweep}", f"{args.setup} : {args.sweep}", args.setup]:
                try:
                    app.odesign.ExportNetworkData(
                        variation,
                        [solution],
                        3,
                        str(touchstone).replace("\\", "/"),
                        ["all"],
                        True,
                        50,
                        "S",
                        -1,
                        0,
                        15,
                        False,
                        False,
                        False,
                    )
                    exists = touchstone.exists()
                    size = touchstone.stat().st_size if exists else 0
                    attempts.append(
                        {
                            "method": "odesign.ExportNetworkData",
                            "variation": variation,
                            "solution": solution,
                            "exists": exists,
                            "size": size,
                        }
                    )
                    if exists and size > 0:
                        exported = str(touchstone)
                        break
                except Exception as exc:
                    attempts.append(
                        {
                            "method": "odesign.ExportNetworkData",
                            "variation": variation,
                            "solution": solution,
                            "error": str(exc),
                        }
                    )
            if exported:
                break
        if not exported:
            try:
                exported = app.export_touchstone(
                    setup=args.setup,
                    sweep=args.sweep,
                    output_file=str(touchstone),
                    renormalization=True,
                    impedance=50,
                )
                attempts.append({"method": "export_touchstone", "result": str(exported)})
            except Exception as exc:
                attempts.append({"method": "export_touchstone", "error": str(exc)})
        if not _touchstone_valid(touchstone):
            auto_candidates = scan_auto_export_candidates(touchstone)
            attempts.append({"method": "auto_export_completion_scan", "candidates": auto_candidates})
            if auto_candidates:
                first_candidate = Path(auto_candidates[0])
                shutil.copyfile(first_candidate, touchstone)
                attempts[-1]["copied_to_touchstone"] = str(touchstone)
        summary["exported"] = str(exported)
        if not _touchstone_valid(touchstone):
            try:
                networks = app.get_touchstone_data(setup=args.setup, sweep=args.sweep)
                if networks and len(networks) > 0 and len(getattr(networks[0], "f", [])) <= 1:
                    alt_networks = app.get_touchstone_data(setup=f"{args.setup} : {args.sweep}", sweep=None)
                    attempts.append(
                        {
                            "method": "get_touchstone_data_alt_solution",
                            "count": len(alt_networks) if alt_networks else 0,
                            "frequency_points": len(getattr(alt_networks[0], "f", [])) if alt_networks else 0,
                        }
                    )
                    if alt_networks and len(getattr(alt_networks[0], "f", [])) > len(getattr(networks[0], "f", [])):
                        networks = alt_networks
                if networks is False:
                    raise RuntimeError("get_touchstone_data returned False")
                attempts.append({"method": "get_touchstone_data", "count": len(networks)})
                if not networks:
                    raise RuntimeError("get_touchstone_data returned no networks")
                network = networks[0]
                network.write_touchstone(str(touchstone.with_suffix("")))
                if not touchstone.exists():
                    candidates = sorted(touchstone.parent.glob(f"{touchstone.stem}.s*p"))
                    if candidates:
                        shutil.copyfile(candidates[0], touchstone)
                attempts[-1]["port_names"] = list(getattr(network, "port_names", []))
                attempts[-1]["frequency_points"] = len(getattr(network, "f", []))
            except Exception as exc:
                attempts.append({"method": "get_touchstone_data", "error": str(exc)})
        summary["export_attempts"] = attempts
        summary["touchstone_exists"] = touchstone.exists()
        summary["touchstone_size"] = touchstone.stat().st_size if touchstone.exists() else 0
        classify_export_failure(summary)
        try:
            app.save_project()
            summary["save_after_export"] = True
        except Exception as exc:
            summary["save_after_export_warning"] = str(exc)
    finally:
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        try:
            app.release_desktop(close_projects=True, close_desktop=bool(args.non_graphical and not args.keep_desktop_open))
        except Exception as exc:
            summary["release_warning"] = str(exc)
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if _touchstone_valid(touchstone) else 2


if __name__ == "__main__":
    raise SystemExit(main())
