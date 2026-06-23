from __future__ import annotations

import argparse
import json
import math
import shutil
import traceback
from pathlib import Path

from ansys.aedt.core import Hfss3dLayout
from pyedb import Edb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create HFSS 3D Layout ports, solve, and export S-parameters.")
    parser.add_argument(
        "--source-aedb",
        required=True,
        help="Input AEDB path.",
    )
    parser.add_argument(
        "--work-aedb",
        required=True,
        help="Working AEDB path.",
    )
    parser.add_argument(
        "--touchstone",
        required=True,
        help="Output Touchstone path.",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help="Output summary JSON path.",
    )
    parser.add_argument("--version", default="2025.1")
    parser.add_argument(
        "--design",
        default=None,
        help="HFSS 3D Layout design name. Leave unset to use the design imported from the AEDB cell.",
    )
    parser.add_argument("--setup", default="Setup1")
    parser.add_argument("--sweep", default="Sweep1")
    parser.add_argument("--adaptive-ghz", type=float, default=5.0)
    parser.add_argument("--start-ghz", type=float, default=0.1)
    parser.add_argument("--stop-ghz", type=float, default=10.0)
    parser.add_argument("--points", type=int, default=21)
    parser.add_argument("--sweep-type", choices=["Discrete", "Interpolating", "Fast"], default="Discrete")
    parser.add_argument("--port-method", choices=["edb_gap", "edb_edge", "component_net"], default="edb_gap")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--skip-aedt-open", action="store_true")
    parser.add_argument("--skip-solve", action="store_true")
    return parser.parse_args()


def copy_aedb(source: Path, dest: Path, overwrite: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if dest.exists():
        if not overwrite:
            raise FileExistsError(f"Destination AEDB exists. Pass --overwrite: {dest}")
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def path_center_line(path_primitive) -> list[list[float]]:
    return path_primitive.get_center_line()


def names_from_mapping_or_list(value) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return sorted(str(item) for item in value)


def resolve_stackup_layer_name(edb, requested: str) -> str:
    requested_lower = str(requested).lower()
    for layer_name in names_from_mapping_or_list(edb.stackup.layers):
        if layer_name.lower() == requested_lower:
            return layer_name
    return requested


def primitive_points_m(primitive) -> list[tuple[float, float]]:
    points_attr = getattr(primitive, "points", None)
    raw_points = points_attr() if callable(points_attr) else points_attr
    if isinstance(raw_points, tuple) and len(raw_points) == 2:
        xs, ys = raw_points
        return [(float(x), float(y)) for x, y in zip(xs, ys)]
    if raw_points:
        return [(float(point[0]), float(point[1])) for point in raw_points]
    polygon_data = getattr(primitive, "polygon_data", None)
    if polygon_data is not None and getattr(polygon_data, "points", None):
        return [(float(point[0]), float(point[1])) for point in polygon_data.points]
    return []


def closest_point_on_segment_m(
    target: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    endpoint_margin: float = 1e-9,
) -> tuple[float, tuple[float, float], float]:
    sx, sy = start
    ex, ey = end
    tx, ty = target
    dx = ex - sx
    dy = ey - sy
    length2 = dx * dx + dy * dy
    if length2 <= 0:
        return math.inf, start, 0.0
    t = ((tx - sx) * dx + (ty - sy) * dy) / length2
    t = max(0.0, min(1.0, t))
    length = math.sqrt(length2)
    if length > 2 * endpoint_margin:
        t = max(endpoint_margin / length, min(1.0 - endpoint_margin / length, t))
    px = sx + t * dx
    py = sy + t * dy
    return math.hypot(tx - px, ty - py), (px, py), t


def find_signal_paths(edb) -> list:
    signal_paths = [
        primitive
        for primitive in edb.modeler.primitives
        if getattr(primitive, "layer_name", "") == "f.cu"
        and getattr(primitive, "net_name", "") == "SIG_50OHM"
        and hasattr(primitive, "create_edge_port")
    ]
    if not signal_paths:
        raise RuntimeError("No f.cu SIG_50OHM path primitives found for port creation.")
    return signal_paths


def find_signal_polygon_primitives(edb) -> list:
    signal_primitives = [
        primitive
        for primitive in edb.modeler.primitives
        if getattr(primitive, "layer_name", "").lower() == "f.cu"
        and getattr(primitive, "net_name", "") == "SIG_50OHM"
        and len(primitive_points_m(primitive)) >= 2
    ]
    if not signal_primitives:
        raise RuntimeError("No f.cu SIG_50OHM polygon/rectangle primitives found for port creation.")
    return signal_primitives


def select_extreme_polygon_edge(signal_primitives: list, side: str) -> dict[str, object]:
    all_points = [point for primitive in signal_primitives for point in primitive_points_m(primitive)]
    if side == "left":
        target_x = min(point[0] for point in all_points)
    elif side == "right":
        target_x = max(point[0] for point in all_points)
    else:
        raise ValueError(side)
    # Use the median Y of signal metal points so the selected edge lands on the
    # launch edge rather than a corner when wide launch pads are present.
    y_values = sorted(point[1] for point in all_points)
    target_y = y_values[len(y_values) // 2]
    target = (target_x, target_y)
    candidates = []
    for primitive in signal_primitives:
        points = primitive_points_m(primitive)
        closed_points = points + [points[0]]
        for edge_index, (start, end) in enumerate(zip(closed_points, closed_points[1:])):
            distance, edge_point, edge_t = closest_point_on_segment_m(target, start, end)
            candidates.append(
                {
                    "distance_m": distance,
                    "edge_point_m": edge_point,
                    "edge_t": edge_t,
                    "edge_index": edge_index,
                    "primitive": primitive,
                    "primitive_id": getattr(primitive, "id", None),
                    "layer_name": getattr(primitive, "layer_name", None),
                    "target_m": target,
                }
            )
    return min(candidates, key=lambda item: item["distance_m"])


def sorted_signal_launch_paths(signal_paths: list) -> tuple:
    def min_x(primitive) -> float:
        return min(point[0] for point in path_center_line(primitive))

    def max_x(primitive) -> float:
        return max(point[0] for point in path_center_line(primitive))

    left_path = min(signal_paths, key=min_x)
    right_path = max(signal_paths, key=max_x)
    return left_path, right_path


def add_microstrip_gap_ports(aedb_path: Path, version: str) -> dict[str, object]:
    edb = Edb(str(aedb_path), isreadonly=False, version=version)
    try:
        try:
            signal_paths = find_signal_paths(edb)
        except RuntimeError:
            return add_microstrip_polygon_gap_ports_to_open_edb(edb)
        left_path, right_path = sorted_signal_launch_paths(signal_paths)

        existing_excitations = set(getattr(edb.hfss, "excitations", {}).keys())
        created = []
        if "Port1" not in existing_excitations:
            created.append(left_path.create_edge_port("Port1", position="Start", port_type="Gap", reference_layer="b.cu"))
        if "Port2" not in existing_excitations:
            created.append(right_path.create_edge_port("Port2", position="End", port_type="Gap", reference_layer="b.cu"))

        circuit_flags = {}
        for port_name, excitation in getattr(edb.hfss, "excitations", {}).items():
            if port_name in {"Port1", "Port2"} and hasattr(excitation, "is_circuit_port"):
                excitation.is_circuit_port = True
                circuit_flags[port_name] = bool(excitation.is_circuit_port)

        edb.save()
        return {
            "port_method": "edb_gap",
            "signal_paths": [
                {
                    "id": primitive.id,
                    "width_m": getattr(primitive, "width", None),
                    "center_line_m": path_center_line(primitive),
                }
                for primitive in signal_paths
            ],
            "port_policy": {
                "Port1": {
                    "primitive_id": left_path.id,
                    "position": "Start",
                    "coordinate_m": path_center_line(left_path)[0],
                    "signal_net": "SIG_50OHM",
                    "reference_layer": "b.cu",
                    "reference_net": "GND",
                    "type": "Circuit gap edge port",
                },
                "Port2": {
                    "primitive_id": right_path.id,
                    "position": "End",
                    "coordinate_m": path_center_line(right_path)[-1],
                    "signal_net": "SIG_50OHM",
                    "reference_layer": "b.cu",
                    "reference_net": "GND",
                    "type": "Circuit gap edge port",
                },
            },
            "circuit_port_flags": circuit_flags,
            "created_ports": [str(item[0] if isinstance(item, tuple) else item) for item in created],
            "excitations_after": list(getattr(edb.hfss, "excitations", {}).keys()),
            "note": "Component coax ports are not used because this coupon has no via or bondwire inside a coax port region.",
        }
    finally:
        edb.close()


def add_microstrip_polygon_gap_ports_to_open_edb(edb) -> dict[str, object]:
    signal_primitives = find_signal_polygon_primitives(edb)
    left = select_extreme_polygon_edge(signal_primitives, "left")
    right = select_extreme_polygon_edge(signal_primitives, "right")
    reference_layer = resolve_stackup_layer_name(edb, "B.Cu")

    existing_excitations = set(getattr(edb.hfss, "excitations", {}).keys())
    created = []
    if "Port1" not in existing_excitations:
        created.append(
            edb.hfss.create_edge_port_vertical(
                left["primitive_id"],
                list(left["edge_point_m"]),
                port_name="Port1",
                impedance=50.0,
                reference_layer=reference_layer,
                hfss_type="Gap",
            )
        )
    if "Port2" not in existing_excitations:
        created.append(
            edb.hfss.create_edge_port_vertical(
                right["primitive_id"],
                list(right["edge_point_m"]),
                port_name="Port2",
                impedance=50.0,
                reference_layer=reference_layer,
                hfss_type="Gap",
            )
        )

    circuit_flags = {}
    for port_name, excitation in getattr(edb.hfss, "excitations", {}).items():
        if port_name in {"Port1", "Port2"} and hasattr(excitation, "is_circuit_port"):
            excitation.is_circuit_port = True
            circuit_flags[port_name] = bool(excitation.is_circuit_port)

    edb.save()
    return {
        "port_method": "edb_polygon_gap",
        "signal_primitives": [
            {
                "id": getattr(primitive, "id", None),
                "layer": getattr(primitive, "layer_name", None),
                "net": getattr(primitive, "net_name", None),
                "point_count": len(primitive_points_m(primitive)),
            }
            for primitive in signal_primitives
        ],
        "port_policy": {
            "Port1": {
                "primitive_id": left["primitive_id"],
                "edge_index": left["edge_index"],
                "coordinate_m": list(left["edge_point_m"]),
                "signal_net": "SIG_50OHM",
                "reference_layer": reference_layer,
                "reference_net": "GND",
                "type": "Circuit gap vertical edge port",
            },
            "Port2": {
                "primitive_id": right["primitive_id"],
                "edge_index": right["edge_index"],
                "coordinate_m": list(right["edge_point_m"]),
                "signal_net": "SIG_50OHM",
                "reference_layer": reference_layer,
                "reference_net": "GND",
                "type": "Circuit gap vertical edge port",
            },
        },
        "circuit_port_flags": circuit_flags,
        "created_ports": [str(item[0] if isinstance(item, tuple) else item) for item in created],
        "excitations_after": list(getattr(edb.hfss, "excitations", {}).keys()),
        "note": "Path primitives were not available; ports were attached to nearest signal polygon edges.",
    }


def add_microstrip_ports(aedb_path: Path, version: str) -> dict[str, object]:
    edb = Edb(str(aedb_path), isreadonly=False, version=version)
    try:
        signal_paths = find_signal_paths(edb)
        left_path, right_path = sorted_signal_launch_paths(signal_paths)

        existing_excitations = set(getattr(edb.hfss, "excitations", {}).keys())
        created = []
        if "Port1" not in existing_excitations:
            created.append(left_path.create_edge_port("Port1", position="Start", port_type="Wave"))
        if "Port2" not in existing_excitations:
            created.append(right_path.create_edge_port("Port2", position="End", port_type="Wave"))

        edb.save()
        port_summary = {
            "signal_paths": [
                {
                    "id": primitive.id,
                    "width_m": getattr(primitive, "width", None),
                    "center_line_m": path_center_line(primitive),
                }
                for primitive in signal_paths
            ],
            "port_policy": {
                "Port1": {
                    "primitive_id": left_path.id,
                    "position": "Start",
                    "coordinate_m": path_center_line(left_path)[0],
                    "signal_net": "SIG_50OHM",
                    "reference_net": "GND",
                    "type": "Wave",
                },
                "Port2": {
                    "primitive_id": right_path.id,
                    "position": "End",
                    "coordinate_m": path_center_line(right_path)[-1],
                    "signal_net": "SIG_50OHM",
                    "reference_net": "GND",
                    "type": "Wave",
                },
            },
            "created_ports": [str(item[0] if isinstance(item, tuple) else item) for item in created],
            "excitations_after": list(getattr(edb.hfss, "excitations", {}).keys()),
        }
        return port_summary
    finally:
        edb.close()


def setup_and_solve(args: argparse.Namespace) -> dict[str, object]:
    def safe_save_project() -> dict[str, object]:
        try:
            return {"ok": bool(app.save_project())}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}

    def safe_port_list() -> list[str]:
        try:
            return list(app.port_list)
        except Exception:
            return []

    def safe_sweeps() -> list[str]:
        try:
            return list(app.get_sweeps(args.setup))
        except Exception:
            return []

    app = Hfss3dLayout(
        project=str(Path(args.work_aedb)),
        design=args.design,
        version=args.version,
        non_graphical=args.non_graphical,
        new_desktop=True,
        close_on_exit=False,
    )
    try:
        if args.port_method == "component_net" and not app.port_list:
            app.create_ports_on_component_by_nets("J1", ["SIG_50OHM"])
            app.create_ports_on_component_by_nets("J2", ["SIG_50OHM"])

        if args.setup not in app.setup_names:
            setup = app.create_setup(
                name=args.setup,
                MeshSizeFactor=2,
                SingleFrequencyDataList__AdaptiveFrequency=f"{args.adaptive_ghz}GHz",
            )
        else:
            setup = app.get_setup(args.setup)

        sweep_names = [sweep.name for sweep in setup.sweeps]
        if args.sweep not in sweep_names:
            app.create_linear_count_sweep(
                setup=args.setup,
                unit="GHz",
                start_frequency=args.start_ghz,
                stop_frequency=args.stop_ghz,
                num_of_freq_points=args.points,
                name=args.sweep,
                save_fields=False,
                sweep_type=args.sweep_type,
                interpolation_tol_percent=1.0,
                interpolation_max_solutions=60,
            )

        app.set_export_touchstone(
            file_format="TouchStone1.0",
            enforce_passivity=True,
            use_common_ground=True,
            renormalize=True,
            impedance=50.0,
            touchstone_output="MA",
            units="GHz",
        )
        auto_export_dir = Path(args.touchstone).parent
        auto_export_status = bool(app.export_touchstone_on_completion(True, str(auto_export_dir)))
        opened_ports = safe_port_list()
        if args.port_method != "component_net" and not opened_ports:
            raise RuntimeError(
                "No HFSS 3D Layout ports were visible after opening the AEDB. "
                "Do not force a generic design name such as 'PCB' unless it is the imported AEDB cell. "
                "Leave --design unset or use the imported design name from the import summary, then verify port_list "
                "before solving."
            )
        save_attempts = [{"stage": "before_solve", **safe_save_project()}]
        solved = False
        touchstone = False
        export_attempts = []
        if not args.skip_solve:
            solved = bool(app.analyze_setup(args.setup))
            for setup_name, sweep_name in [(args.setup, args.sweep), (args.setup, None)]:
                try:
                    exported = app.export_touchstone(
                        setup=setup_name,
                        sweep=sweep_name,
                        output_file=str(Path(args.touchstone)),
                        renormalization=True,
                        impedance=50,
                    )
                    export_attempts.append(
                        {"method": "native_export_touchstone", "setup": setup_name, "sweep": sweep_name, "result": str(exported)}
                    )
                    if exported and Path(exported).exists():
                        touchstone = exported
                        break
                except Exception as exc:
                    export_attempts.append(
                        {
                            "method": "native_export_touchstone",
                            "setup": setup_name,
                            "sweep": sweep_name,
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )

            if not touchstone:
                try:
                    networks = app.get_touchstone_data(setup=args.setup, sweep=args.sweep)
                    export_attempts.append({"method": "get_touchstone_data", "count": len(networks)})
                    if networks:
                        output = Path(args.touchstone)
                        networks[0].write_touchstone(str(output.with_suffix("")))
                        if output.exists():
                            touchstone = str(output)
                except Exception as exc:
                    export_attempts.append(
                        {
                            "method": "get_touchstone_data_write_touchstone",
                            "error": str(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )
        save_attempts.append({"stage": "after_export", **safe_save_project()})
        return {
            "project_file": app.project_file,
            "design": app.design_name,
            "ports": safe_port_list(),
            "setups": app.setup_names,
            "sweeps": safe_sweeps(),
            "solved": solved,
            "touchstone": str(touchstone) if touchstone else False,
            "export_attempts": export_attempts,
            "auto_export": {
                "enabled": auto_export_status,
                "output_dir": str(auto_export_dir),
            },
            "save_attempts": save_attempts,
        }
    finally:
        # Keep desktop open only when graphical; non-graphical runs can release the process.
        if args.non_graphical:
            app.release_desktop(close_projects=False, close_desktop=True)


def main() -> None:
    args = parse_args()
    source = Path(args.source_aedb)
    work_aedb = Path(args.work_aedb)
    copy_aedb(source, work_aedb, args.overwrite)

    if args.port_method == "edb_gap":
        port_summary = add_microstrip_gap_ports(work_aedb, args.version)
    elif args.port_method == "edb_edge":
        port_summary = add_microstrip_ports(work_aedb, args.version)
    else:
        port_summary = {
            "port_method": "component_net",
            "component_ports": [
                {"component": "J1", "signal_net": "SIG_50OHM", "reference_net": "GND"},
                {"component": "J2", "signal_net": "SIG_50OHM", "reference_net": "GND"},
            ],
            "note": "Ports are created in AEDT HFSS 3D Layout with create_ports_on_component_by_nets.",
        }
    if args.skip_aedt_open:
        solve_summary = {
            "project_file": None,
            "design": "PCB",
            "ports": [],
            "setups": [],
            "sweeps": [],
            "solved": False,
            "touchstone": False,
            "export_attempts": [],
            "note": "AEDT project open was skipped after EDB port creation.",
        }
    else:
        try:
            solve_summary = setup_and_solve(args)
        except Exception as exc:
            solve_summary = {
                "project_file": None,
                "design": args.design or "imported_aedb_cell",
                "ports": [],
                "setups": [],
                "sweeps": [],
                "solved": False,
                "touchstone": False,
                "export_attempts": [],
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

    summary = {
        "ok": bool(args.skip_solve or (solve_summary.get("solved") and solve_summary.get("touchstone"))),
        "source_aedb": str(source),
        "work_aedb": str(work_aedb),
        "aedt_version": args.version,
        "setup": args.setup,
        "sweep": {
            "name": args.sweep,
            "start_ghz": args.start_ghz,
            "stop_ghz": args.stop_ghz,
            "points": args.points,
            "type": args.sweep_type,
        },
        "ports": port_summary,
        "solve": solve_summary,
        "touchstone": str(Path(args.touchstone)),
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
