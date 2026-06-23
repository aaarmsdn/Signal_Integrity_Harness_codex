from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a GUI-openable AEDT HFSS 3D Layout project from KiCad ODB++ or IPC-2581.")
    parser.add_argument(
        "--odb",
        required=True,
        help="Input ODB++ zip exported from KiCad or another PCB tool.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Output AEDT project path.",
    )
    parser.add_argument("--ipc2581", default=None, help="Optional IPC-2581 fallback file exported from KiCad.")
    parser.add_argument("--kicad-board", default=None, help="Optional KiCad .kicad_pcb fallback source.")
    parser.add_argument("--port-intents", default=None, help="Optional SIPI harness port-intent JSON to apply after import.")
    parser.add_argument(
        "--port-method",
        choices=["circuit", "pin", "edb_polygon_edge", "edb_path_edge"],
        default="edb_polygon_edge",
        help=(
            "Port creation method. Default is edb_polygon_edge because HFSS 3D Layout coordinate/pin "
            "ports can be visible but misplaced or non-exportable after KiCad/AEDB import. Use circuit "
            "or pin only as an explicit override after manual/tool verification. Use edb_path_edge for "
            "trace/path primitives if polygon-edge creation is not available."
        ),
    )
    parser.add_argument(
        "--edge-port-type",
        choices=["Gap", "Wave"],
        default="Gap",
        help="AEDB edge-port type for edge-port methods. Try Wave only as a documented edge-port variant.",
    )
    parser.add_argument(
        "--allow-coordinate-port-override",
        action="store_true",
        help=(
            "Permit coordinate circuit/pin ports. This is a manual/debug override only. "
            "The normal harness path must use edb_polygon_edge ports."
        ),
    )
    parser.add_argument(
        "--allow-path-edge-port-override",
        action="store_true",
        help=(
            "Permit edb_path_edge ports as a manual/debug override. Normal harness "
            "runs must use edb_polygon_edge; path-edge ports can bind to long trace "
            "side edges or the wrong Start/End edge and should not be used for "
            "valid compliance handoff."
        ),
    )
    parser.add_argument(
        "--direct-edb-fallback",
        action="store_true",
        help="Build a minimal AEDB directly from --kicad-board if native imports validate as empty.",
    )
    parser.add_argument(
        "--prefer-direct-edb",
        action="store_true",
        help="Use the KiCad direct AEDB builder first and skip native ODB++/IPC-2581 import attempts.",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help="Output summary JSON path.",
    )
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--temp-dir", default=None, help="Optional temp directory for AEDT/PyEDB child processes.")
    parser.add_argument("--min-nets", type=int, default=1)
    parser.add_argument("--min-layers", type=int, default=1)
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
            pyaedt_settings.global_log_file_name = str(temp_path / "pyaedt_import.log")
            pyaedt_settings.aedt_log_file = str(temp_path / "aedt_import.log")
    except Exception:
        pass
    try:
        from pyedb.generic.settings import settings as pyedb_settings

        pyedb_settings.enable_global_log_file = True
        pyedb_settings.enable_local_log_file = False
        if temp_dir:
            pyedb_settings.global_log_file_name = str(Path(temp_dir).resolve() / "pyedb_import.log")
    except Exception:
        pass


def coordinate_to_meter(value: object, unit: str) -> float:
    scale = {"m": 1.0, "meter": 1.0, "mm": 1e-3, "mil": 25.4e-6, "um": 1e-6}
    if isinstance(value, (int, float)):
        return float(value) * scale.get(unit.lower(), 1e-3)
    text = str(value).strip()
    lower = text.lower()
    for suffix, factor in sorted(scale.items(), key=lambda item: len(item[0]), reverse=True):
        if lower.endswith(suffix):
            return float(text[: -len(suffix)].strip()) * factor
    return float(text) * scale.get(unit.lower(), 1e-3)


def coordinate_to_editor_value(value: object, unit: str) -> str:
    """Return an AEDT editor-coordinate string with units.

    HFSS 3D Layout editor macros such as CreateCircuitPort interpret bare floats
    inconsistently across APIs and AEDT versions. Passing SI-meter floats can
    silently place ports near the origin while still creating visible port labels.
    Use explicit unit-bearing strings for geometry-facing editor calls.
    """
    if isinstance(value, (int, float)):
        return f"{float(value):.12g}{unit}"
    text = str(value).strip()
    lower = text.lower()
    known_units = ("meter", "mil", "mm", "um", "m")
    if any(lower.endswith(suffix) for suffix in known_units):
        return text
    return f"{text}{unit}"


def prepare_odb_input(odb: Path) -> tuple[Path, bool]:
    if odb.suffix.lower() != ".zip":
        return odb, False
    extracted = odb.with_suffix("")
    if extracted.exists():
        shutil.rmtree(extracted)
    extracted.mkdir(parents=True)
    with zipfile.ZipFile(odb, "r") as archive:
        archive.extractall(extracted)
    return extracted, True


def remove_project_family(project: Path) -> None:
    for suffix in [".aedt", ".aedb", ".aedtresults"]:
        item = project.with_suffix(suffix)
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    lock = Path(str(project) + ".lock")
    if lock.exists():
        lock.unlink()


def remove_aedt_shell(project: Path) -> None:
    """Remove stale AEDT shell files while preserving the AEDB database.

    Native ODB/IPC import creates an `.aedt` next to the `.aedb`. If ports are
    then repaired directly in AEDB, opening `Hfss3dLayout(project=<aedb>)` can
    still bind to the stale project shell and silently drop the newly saved EDB
    excitations. Delete only the AEDT shell/results before saving a fresh AEDT
    from the mutated AEDB.
    """
    for suffix in [".aedt", ".aedtresults"]:
        item = project.with_suffix(suffix)
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    lock = Path(str(project) + ".lock")
    if lock.exists():
        lock.unlink()


def names_from_mapping_or_list(value) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return sorted(str(item) for item in value)


def inspect_aedb(aedb: Path, version: str) -> dict[str, object]:
    from pyedb import Edb

    edb = Edb(edbpath=str(aedb), isreadonly=True, version=version)
    try:
        nets = names_from_mapping_or_list(edb.nets.nets)
        layers = names_from_mapping_or_list(edb.stackup.layers)
        component_source = getattr(edb.components, "components", None)
        if component_source is None:
            component_source = getattr(edb.components, "instances", {})
        components = names_from_mapping_or_list(component_source)
        primitive_layers_by_net: dict[str, list[str]] = {}
        primitive_counts_by_net_layer: dict[str, dict[str, int]] = {}
        for primitive in list(edb.modeler.primitives):
            net_name = str(getattr(primitive, "net_name", ""))
            layer_name = str(getattr(primitive, "layer_name", ""))
            if not net_name or not layer_name:
                continue
            primitive_counts_by_net_layer.setdefault(net_name, {})
            primitive_counts_by_net_layer[net_name][layer_name] = (
                primitive_counts_by_net_layer[net_name].get(layer_name, 0) + 1
            )
        for net_name, layer_counts in primitive_counts_by_net_layer.items():
            primitive_layers_by_net[net_name] = sorted(layer_counts.keys())
        primitive_overlap_check = check_primitive_overlaps(edb)
        return {
            "net_count": len(nets),
            "nets": nets,
            "layer_count": len(layers),
            "layers": layers,
            "component_count": len(components),
            "components": components,
            "primitive_layers_by_net": primitive_layers_by_net,
            "primitive_counts_by_net_layer": primitive_counts_by_net_layer,
            "primitive_overlap_check": primitive_overlap_check,
        }
    finally:
        edb.close()


def aedb_import_is_valid(inspection: dict[str, object], min_nets: int, min_layers: int) -> bool:
    overlap_check = inspection.get("primitive_overlap_check")
    overlap_ok = not isinstance(overlap_check, dict) or overlap_check.get("result") == "PASS"
    return (
        int(inspection.get("net_count") or 0) >= min_nets
        and int(inspection.get("layer_count") or 0) >= min_layers
        and overlap_ok
    )


def primitive_points_m(primitive) -> list[tuple[float, float]]:
    raw_points = None
    points_attr = getattr(primitive, "points", None)
    if callable(points_attr):
        raw_points = points_attr()
    elif points_attr is not None:
        raw_points = points_attr
    if isinstance(raw_points, tuple) and len(raw_points) == 2:
        xs, ys = raw_points
        return [(float(x), float(y)) for x, y in zip(xs, ys)]
    if raw_points:
        return [(float(point[0]), float(point[1])) for point in raw_points]
    polygon_data = getattr(primitive, "polygon_data", None)
    if polygon_data is not None and getattr(polygon_data, "points", None):
        return [(float(point[0]), float(point[1])) for point in polygon_data.points]
    return []


def polygon_bbox_m(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def bboxes_overlap_m(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    tolerance_m: float = 1e-12,
) -> bool:
    return not (
        a[2] < b[0] - tolerance_m
        or b[2] < a[0] - tolerance_m
        or a[3] < b[1] - tolerance_m
        or b[3] < a[1] - tolerance_m
    )


def point_on_segment_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance_m: float = 1e-12,
) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    length = math.hypot(bx - ax, by - ay)
    if length <= tolerance_m:
        return math.hypot(px - ax, py - ay) <= tolerance_m
    cross = abs((px - ax) * (by - ay) - (py - ay) * (bx - ax))
    if cross / length > tolerance_m:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    return -tolerance_m <= dot <= length * length + tolerance_m


def point_in_polygon_m(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if point_on_segment_m(point, previous, current):
            return True
        if (current[1] > y) != (previous[1] > y):
            x_cross = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < x_cross:
                inside = not inside
        previous = current
    return inside


def segments_intersect_m(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
    tolerance_m: float = 1e-12,
) -> bool:
    def orient(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)
    if o1 * o2 < -tolerance_m and o3 * o4 < -tolerance_m:
        return True
    return (
        abs(o1) <= tolerance_m
        and point_on_segment_m(b1, a1, a2, tolerance_m)
        or abs(o2) <= tolerance_m
        and point_on_segment_m(b2, a1, a2, tolerance_m)
        or abs(o3) <= tolerance_m
        and point_on_segment_m(a1, b1, b2, tolerance_m)
        or abs(o4) <= tolerance_m
        and point_on_segment_m(a2, b1, b2, tolerance_m)
    )


def polygon_overlap_m(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    if not bboxes_overlap_m(polygon_bbox_m(a), polygon_bbox_m(b)):
        return False
    a_edges = list(zip(a, a[1:] + a[:1]))
    b_edges = list(zip(b, b[1:] + b[:1]))
    for a1, a2 in a_edges:
        for b1, b2 in b_edges:
            if segments_intersect_m(a1, a2, b1, b2):
                return True
    return point_in_polygon_m(a[0], b) or point_in_polygon_m(b[0], a)


def check_primitive_overlaps(edb, max_violations: int = 100) -> dict[str, object]:
    primitives: list[dict[str, object]] = []
    for primitive in list(edb.modeler.primitives):
        net_name = str(getattr(primitive, "net_name", ""))
        layer_name = str(getattr(primitive, "layer_name", ""))
        points = primitive_points_m(primitive)
        if not net_name or not layer_name or len(points) < 3:
            continue
        primitives.append(
            {
                "id": str(getattr(primitive, "id", "")),
                "net_name": net_name,
                "layer_name": layer_name,
                "points": points,
                "bbox_m": polygon_bbox_m(points),
            }
        )
    violations = []
    for index, a in enumerate(primitives):
        for b in primitives[index + 1 :]:
            if a["layer_name"] != b["layer_name"] or a["net_name"] == b["net_name"]:
                continue
            if not bboxes_overlap_m(a["bbox_m"], b["bbox_m"]):
                continue
            if not polygon_overlap_m(a["points"], b["points"]):
                continue
            violations.append(
                {
                    "rule": "aedb_same_layer_different_net_primitive_overlap",
                    "layer": a["layer_name"],
                    "a": {"id": a["id"], "net": a["net_name"], "bbox_m": a["bbox_m"]},
                    "b": {"id": b["id"], "net": b["net_name"], "bbox_m": b["bbox_m"]},
                }
            )
            if len(violations) >= max_violations:
                break
        if len(violations) >= max_violations:
            break
    return {
        "result": "PASS" if not violations else "FAIL",
        "primitive_count_checked": len(primitives),
        "violation_count": len(violations),
        "violations": violations,
        "note": (
            "Post-conversion AEDB gate. Blocks same-layer overlap between "
            "different-net polygon primitives created by ODB/IPC import or "
            "direct KiCad-to-AEDB fallback, including launch/via pad polygons."
        ),
    }


def primitive_centerline_points_m(primitive) -> list[tuple[float, float]]:
    center_line = getattr(primitive, "center_line", None)
    if callable(center_line):
        center_line = center_line()
    if center_line:
        return [(float(point[0]), float(point[1])) for point in center_line]
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


def resolve_stackup_layer_name(edb, requested: str) -> str:
    requested_lower = str(requested).lower()
    for layer_name in names_from_mapping_or_list(edb.stackup.layers):
        if layer_name.lower() == requested_lower:
            return layer_name
    return requested


def normalize_layout_layer_name(requested: object, actual_layers: list[str] | None = None) -> str:
    requested_text = str(requested)
    if not actual_layers:
        return requested_text
    requested_lower = requested_text.lower()
    for layer_name in actual_layers:
        if str(layer_name).lower() == requested_lower:
            return str(layer_name)
    requested_compact = "".join(ch for ch in requested_lower if ch.isalnum())
    for layer_name in actual_layers:
        layer_compact = "".join(ch for ch in str(layer_name).lower() if ch.isalnum())
        if layer_compact == requested_compact:
            return str(layer_name)
    return requested_text


def compact_layer_name(layer_name: object) -> str:
    return "".join(ch for ch in str(layer_name).lower() if ch.isalnum())


def resolve_signal_layer_from_primitives(
    requested_layer: str,
    net: str,
    primitive_layers_by_net: dict[str, list[str]] | None,
) -> tuple[str, bool, list[str]]:
    if not primitive_layers_by_net:
        return requested_layer, True, []
    available_layers = primitive_layers_by_net.get(net) or primitive_layers_by_net.get(net.upper()) or []
    requested_compact = compact_layer_name(requested_layer)
    for layer_name in available_layers:
        if compact_layer_name(layer_name) == requested_compact:
            return str(layer_name), True, available_layers
    if len(available_layers) == 1:
        return str(available_layers[0]), False, available_layers
    return requested_layer, False, available_layers


def choose_reference_layer_for_signal_layer(
    signal_layer: str,
    requested_negative_layer: str,
    actual_layers: list[str] | None,
    layer_was_corrected: bool,
) -> str:
    if not layer_was_corrected:
        return requested_negative_layer
    layer_set = {compact_layer_name(layer): str(layer) for layer in actual_layers or []}
    signal_compact = compact_layer_name(signal_layer)
    if signal_compact in {"fcu", "top"} and "in1cu" in layer_set:
        return layer_set["in1cu"]
    if signal_compact in {"bcu", "bottom"} and "in2cu" in layer_set:
        return layer_set["in2cu"]
    return requested_negative_layer


def select_polygon_edge_for_port(edb, port: dict[str, object], unit: str) -> dict[str, object]:
    target_x = port.get("positive_x", port.get("x"))
    target_y = port.get("positive_y", port.get("y"))
    if target_x is None or target_y is None:
        raise ValueError(
            f"Port {port.get('name')} needs positive_x/positive_y coordinates for AEDB edge-port placement."
        )
    target = (coordinate_to_meter(target_x, unit), coordinate_to_meter(target_y, unit))
    net = str(port.get("net") or port.get("signal_net") or "")
    requested_layer = str(port.get("positive_layer", port.get("pos_layer", ""))).lower()
    max_edge_length_m = float(port.get("max_port_edge_length_mm", 0.30)) * 1e-3
    max_edge_distance_m = float(port.get("max_port_edge_distance_mm", 0.05)) * 1e-3
    candidates = []
    all_net_candidates = []
    for primitive in list(edb.modeler.primitives):
        if str(getattr(primitive, "net_name", "")).lower() != net.lower():
            continue
        points = primitive_points_m(primitive)
        if len(points) < 2:
            continue
        closed_points = points + [points[0]]
        for edge_index, (start, end) in enumerate(zip(closed_points, closed_points[1:])):
            distance, edge_point, edge_t = closest_point_on_segment_m(target, start, end)
            edge_length = math.hypot(end[0] - start[0], end[1] - start[1])
            midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            midpoint_distance = math.hypot(target[0] - midpoint[0], target[1] - midpoint[1])
            is_terminal_like = edge_length <= max_edge_length_m and distance <= max_edge_distance_m
            candidate = {
                "distance_m": distance,
                "midpoint_distance_m": midpoint_distance,
                "edge_length_m": edge_length,
                "is_terminal_like": is_terminal_like,
                "edge_point_m": edge_point,
                "edge_t": edge_t,
                "edge_index": edge_index,
                "primitive": primitive,
                "primitive_id": getattr(primitive, "id", None),
                "layer_name": getattr(primitive, "layer_name", None),
                "requested_layer": requested_layer,
                "layer_matched_intent": str(getattr(primitive, "layer_name", "")).lower() == requested_layer,
            }
            all_net_candidates.append(candidate)
            if candidate["layer_matched_intent"]:
                candidates.append(candidate)
    if not candidates:
        # Prefer a real net primitive over a stale port-intent layer. KiCad/ODB imports can
        # normalize or collapse route layers; a port on a non-existent signal layer becomes a
        # visible label that is not exportable as network data.
        candidates = all_net_candidates
    if not candidates:
        raise RuntimeError(
            f"No polygon/path primitive edge found for port {port.get('name')} net={net} requested_layer={requested_layer}"
        )
    terminal_candidates = [candidate for candidate in candidates if candidate["is_terminal_like"]]
    if not terminal_candidates:
        nearest = min(candidates, key=lambda item: item["distance_m"])
        raise RuntimeError(
            "No terminal-like polygon edge found for "
            f"port {port.get('name')} net={net}. Nearest edge length="
            f"{nearest['edge_length_m'] * 1e3:.4f}mm distance="
            f"{nearest['distance_m'] * 1e3:.4f}mm. This usually means the selector "
            "would attach the port to a long trace side edge instead of a launch/pad edge. "
            "Move positive_x/positive_y to the launch edge or add a small non-overlapping "
            "port tab/pad in the source layout."
        )
    return min(terminal_candidates, key=lambda item: (item["distance_m"], item["midpoint_distance_m"], item["edge_length_m"]))


def select_path_primitive_for_port(
    edb,
    port: dict[str, object],
    unit: str,
    actual_layers: list[str] | None = None,
) -> dict[str, object]:
    target_x = port.get("positive_x", port.get("x"))
    target_y = port.get("positive_y", port.get("y"))
    if target_x is None or target_y is None:
        raise ValueError(
            f"Port {port.get('name')} needs positive_x/positive_y coordinates for AEDB path-edge placement."
        )
    target = (coordinate_to_meter(target_x, unit), coordinate_to_meter(target_y, unit))
    net = str(port.get("net") or port.get("signal_net") or "")
    requested_layer = normalize_layout_layer_name(port.get("positive_layer", port.get("pos_layer", "")), actual_layers)
    requested_compact = compact_layer_name(requested_layer)

    candidates = []
    for primitive in list(edb.modeler.primitives):
        if str(getattr(primitive, "net_name", "")).lower() != net.lower():
            continue
        if not hasattr(primitive, "create_edge_port"):
            continue
        centerline = primitive_centerline_points_m(primitive)
        if len(centerline) < 2:
            continue
        start = centerline[0]
        end = centerline[-1]
        start_distance = math.hypot(target[0] - start[0], target[1] - start[1])
        end_distance = math.hypot(target[0] - end[0], target[1] - end[1])
        position = "Start" if start_distance <= end_distance else "End"
        selected_distance = min(start_distance, end_distance)
        layer_name = str(getattr(primitive, "layer_name", ""))
        candidates.append(
            {
                "primitive": primitive,
                "primitive_id": getattr(primitive, "id", None),
                "net": net,
                "layer_name": layer_name,
                "requested_layer": requested_layer,
                "layer_matched_intent": compact_layer_name(layer_name) == requested_compact,
                "position": position,
                "start_m": list(start),
                "end_m": list(end),
                "distance_to_intent_m": selected_distance,
            }
        )
    if not candidates:
        raise RuntimeError(f"No path primitive with create_edge_port found for port {port.get('name')} net={net}")
    matching = [item for item in candidates if item["layer_matched_intent"]]
    if matching:
        candidates = matching
    return min(candidates, key=lambda item: item["distance_to_intent_m"])


def delete_existing_edb_excitations(edb) -> None:
    for _, excitation in list(getattr(edb.hfss, "excitations", {}).items()):
        try:
            excitation.delete()
        except Exception:
            try:
                excitation._edb_object.Delete()
            except Exception:
                pass


def save_edb_database(edb) -> None:
    if hasattr(edb, "save_edb"):
        edb.save_edb()
    else:
        edb.save()


def compute_edb_primitive_bbox_m(edb) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []
    for primitive in list(edb.modeler.primitives):
        points.extend(primitive_points_m(primitive))
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def has_reference_primitive(edb, reference_net: str, reference_layer: str) -> bool:
    for primitive in list(edb.modeler.primitives):
        if str(getattr(primitive, "net_name", "")).lower() != reference_net.lower():
            continue
        if compact_layer_name(getattr(primitive, "layer_name", "")) == compact_layer_name(reference_layer):
            return True
    return False


def add_reference_plane_rectangle(edb, reference_net: str, reference_layer: str, bbox_m) -> bool:
    if has_reference_primitive(edb, reference_net, reference_layer):
        return False
    if bbox_m is None:
        raise RuntimeError(f"Cannot add {reference_net} reference plane on {reference_layer}; AEDB has no geometry bbox.")
    x0, y0, x1, y1 = bbox_m
    margin_m = 0.5e-3
    lower_left = [f"{(x0 - margin_m) * 1e3:.12g}mm", f"{(y0 - margin_m) * 1e3:.12g}mm"]
    upper_right = [f"{(x1 + margin_m) * 1e3:.12g}mm", f"{(y1 + margin_m) * 1e3:.12g}mm"]
    plane = edb.modeler.create_rectangle(
        layer_name=reference_layer,
        net_name=reference_net,
        lower_left_point=lower_left,
        upper_right_point=upper_right,
    )
    if not plane:
        raise RuntimeError(f"Failed to create {reference_net} reference plane on {reference_layer}")
    return True


def ensure_reference_planes_from_port_intents(
    aedb: Path,
    port_intents: Path,
    version: str,
    actual_layers: list[str],
) -> dict[str, object]:
    from pyedb import Edb

    port_spec = json.loads(port_intents.read_text(encoding="utf-8-sig"))
    requested: dict[tuple[str, str], dict[str, object]] = {}
    reference_nets = sorted(
        {
            str(port.get("reference_net") or "GND")
            for port in port_spec.get("ports", [])
            if port.get("reference_net") or str(port.get("negative_layer", "")).lower() not in {"", "gnd!"}
        }
    )
    signal_nets = sorted(
        {
            str(port.get("net") or port.get("signal_net") or "")
            for port in port_spec.get("ports", [])
            if port.get("net") or port.get("signal_net")
        }
    )
    for port in port_spec.get("ports", []):
        reference_net = str(port.get("reference_net") or "GND")
        requested_layer = port.get("negative_layer", port.get("neg_layer"))
        if not requested_layer:
            continue
        reference_layer = normalize_layout_layer_name(requested_layer, actual_layers)
        requested[(reference_net, reference_layer)] = {
            "reference_net": reference_net,
            "reference_layer": reference_layer,
            "requested_layer": requested_layer,
        }
    if not requested:
        return {"requested": [], "added": [], "existing": [], "skipped": "no_reference_layers_requested"}

    edb = Edb(edbpath=str(aedb), isreadonly=False, version=version)
    try:
        classification = {
            "requested_power_ground_nets": reference_nets,
            "requested_signal_nets": signal_nets,
            "classify_return": None,
            "error": None,
        }
        try:
            classification["classify_return"] = bool(
                edb.nets.classify_nets(power_nets=reference_nets, signal_nets=signal_nets)
            )
        except Exception as exc:
            classification["error"] = str(exc)
        bbox_m = compute_edb_primitive_bbox_m(edb)
        existing = []
        added = []
        for key, item in requested.items():
            reference_net, reference_layer = key
            if has_reference_primitive(edb, reference_net, reference_layer):
                existing.append(item)
                continue
            was_added = add_reference_plane_rectangle(edb, reference_net, reference_layer, bbox_m)
            if was_added:
                added.append({**item, "source": "auto_added_from_port_intent", "bbox_m": list(bbox_m or [])})
        if added:
            save_edb_database(edb)
        elif classification["classify_return"]:
            save_edb_database(edb)
        return {
            "requested": list(requested.values()),
            "existing": existing,
            "added": added,
            "net_classification": classification,
            "bbox_m": list(bbox_m) if bbox_m else None,
        }
    finally:
        edb.close()


def apply_edb_polygon_edge_ports(aedb: Path, port_intents: Path, version: str) -> dict[str, object]:
    from pyedb import Edb

    port_spec = json.loads(port_intents.read_text(encoding="utf-8-sig"))
    unit = str(port_spec.get("unit", "mm"))
    edb = Edb(edbpath=str(aedb), isreadonly=False, version=version)
    try:
        delete_existing_edb_excitations(edb)
        created = []
        failures = []
        selections = []
        ports = port_spec.get("ports", [])
        for index, port in enumerate(ports, start=1):
            try:
                if port.get("type", "circuit") != "circuit":
                    raise ValueError(f"Unsupported port type: {port.get('type')}")
                name = str(port.get("name") or f"Port{index}")
                selected = select_polygon_edge_for_port(edb, port, unit)
                edge_point = selected["edge_point_m"]
                reference_layer = resolve_stackup_layer_name(edb, port.get("negative_layer", port.get("neg_layer")))
                result = edb.hfss.create_edge_port_vertical(
                    selected["primitive_id"],
                    [edge_point[0], edge_point[1]],
                    port_name=name,
                    impedance=float(port.get("impedance_ohm") or port.get("expected_impedance_ohm") or 50),
                    reference_layer=reference_layer,
                    hfss_type="Gap",
                )
                excitation = getattr(edb.hfss, "excitations", {}).get(name)
                circuit_flag = None
                if excitation is not None and hasattr(excitation, "is_circuit_port"):
                    excitation.is_circuit_port = True
                    circuit_flag = bool(excitation.is_circuit_port)
                actual_name = result[0] if isinstance(result, tuple) else name
                created.append(
                    {
                        "intent_name": port.get("name"),
                        "actual_name": actual_name,
                        "net": port.get("net") or port.get("signal_net"),
                        "role": port.get("role"),
                        "x": port.get("x"),
                        "y": port.get("y"),
                        "requested_positive_layer": port.get("positive_layer", port.get("pos_layer")),
                        "positive_layer": selected.get("layer_name"),
                        "negative_layer": port.get("negative_layer", port.get("neg_layer")),
                    }
                )
                selections.append(
                    {
                        "name": name,
                        "net": port.get("net") or port.get("signal_net"),
                        "primitive_id": selected["primitive_id"],
                        "edge_index": selected["edge_index"],
                        "edge_point_m": list(edge_point),
                        "distance_to_intent_m": selected["distance_m"],
                        "requested_layer": selected.get("requested_layer"),
                        "selected_layer": selected.get("layer_name"),
                        "layer_matched_intent": selected.get("layer_matched_intent"),
                        "reference_layer": reference_layer,
                        "circuit_port": circuit_flag,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "port": port.get("name"),
                        "net": port.get("net") or port.get("signal_net"),
                        "error": str(exc),
                    }
                )
        save_edb_database(edb)
        final_ports = list(getattr(edb.hfss, "excitations", {}).keys())
        return {
            "source": str(port_intents),
            "method": "edb_polygon_edge",
            "requested_count": len(ports),
            "created_count": len(created),
            "created": created,
            "failures": failures,
            "port_selections": selections,
            "final_port_list": final_ports,
        }
    finally:
        edb.close()


def apply_edb_path_edge_ports(
    aedb: Path,
    port_intents: Path,
    version: str,
    actual_layers: list[str] | None = None,
    primitive_layers_by_net: dict[str, list[str]] | None = None,
    edge_port_type: str = "Gap",
) -> dict[str, object]:
    from pyedb import Edb

    port_spec = json.loads(port_intents.read_text(encoding="utf-8-sig"))
    unit = str(port_spec.get("unit", "mm"))
    edb = Edb(edbpath=str(aedb), isreadonly=False, version=version)
    try:
        delete_existing_edb_excitations(edb)
        created = []
        failures = []
        selections = []
        ports = port_spec.get("ports", [])
        for index, port in enumerate(ports, start=1):
            try:
                if port.get("type", "circuit") != "circuit":
                    raise ValueError(f"Unsupported port type: {port.get('type')}")
                name = str(port.get("name") or f"Port{index}")
                selected = select_path_primitive_for_port(edb, port, unit, actual_layers=actual_layers)
                requested_negative_layer = normalize_layout_layer_name(
                    port.get("negative_layer", port.get("neg_layer")),
                    actual_layers,
                )
                net_name = str(port.get("net") or port.get("signal_net") or "")
                _, signal_layer_matched_intent, primitive_layers_for_net = resolve_signal_layer_from_primitives(
                    selected["requested_layer"],
                    net_name,
                    primitive_layers_by_net,
                )
                reference_layer = choose_reference_layer_for_signal_layer(
                    selected["layer_name"],
                    requested_negative_layer,
                    actual_layers,
                    layer_was_corrected=not signal_layer_matched_intent,
                )
                reference_layer = resolve_stackup_layer_name(edb, reference_layer)
                if edge_port_type == "Wave":
                    result = selected["primitive"].create_edge_port(
                        name,
                        position=selected["position"],
                        port_type="Wave",
                    )
                else:
                    result = selected["primitive"].create_edge_port(
                        name,
                        position=selected["position"],
                        port_type="Gap",
                        reference_layer=reference_layer,
                    )
                port_object = None
                if isinstance(result, tuple) and len(result) > 1:
                    port_object = result[1]
                elif result is not None:
                    port_object = result
                circuit_flag = None
                if port_object is not None and hasattr(port_object, "is_circuit_port"):
                    port_object.is_circuit_port = True
                    circuit_flag = bool(port_object.is_circuit_port)
                actual_name = name
                if result is not None and getattr(result, "name", None):
                    actual_name = str(result.name)
                created.append(
                    {
                        "intent_name": port.get("name"),
                        "actual_name": actual_name,
                        "net": net_name,
                        "role": port.get("role"),
                        "requested_positive_layer": port.get("positive_layer", port.get("pos_layer")),
                        "positive_layer": selected["layer_name"],
                        "negative_layer": reference_layer,
                        "edge_port_type": edge_port_type,
                        "circuit_port": circuit_flag,
                        "position": selected["position"],
                        "primitive_id": selected["primitive_id"],
                        "signal_layer_matched_intent": signal_layer_matched_intent,
                        "primitive_layers_for_net": primitive_layers_for_net,
                    }
                )
                selections.append(
                    {
                        "name": name,
                        "net": net_name,
                        "primitive_id": selected["primitive_id"],
                        "selected_layer": selected["layer_name"],
                        "requested_layer": selected["requested_layer"],
                        "layer_matched_intent": selected["layer_matched_intent"],
                        "position": selected["position"],
                        "start_m": selected["start_m"],
                        "end_m": selected["end_m"],
                        "distance_to_intent_m": selected["distance_to_intent_m"],
                        "reference_layer": reference_layer,
                        "edge_port_type": edge_port_type,
                        "circuit_port": circuit_flag,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "port": port.get("name"),
                        "net": port.get("net") or port.get("signal_net"),
                        "error": str(exc),
                    }
                )
        save_edb_database(edb)
        final_ports = list(getattr(edb.hfss, "excitations", {}).keys())
        return {
            "source": str(port_intents),
            "method": "edb_path_edge",
            "edge_port_type": edge_port_type,
            "requested_count": len(ports),
            "created_count": len(created),
            "created": created,
            "failures": failures,
            "port_selections": selections,
            "actual_layers": actual_layers or [],
            "primitive_layers_by_net": primitive_layers_by_net or {},
            "final_port_list": final_ports,
        }
    finally:
        edb.close()


def import_candidate(method: str, input_file: Path, project: Path, version: str, non_graphical: bool) -> dict[str, object]:
    from ansys.aedt.core import Hfss3dLayout

    remove_project_family(project)
    aedb = project.with_suffix(".aedb")
    h3d = Hfss3dLayout(
        project=None,
        version=version,
        non_graphical=non_graphical,
        new_desktop=True,
        close_on_exit=False,
    )
    try:
        if method == "odb":
            ok = h3d.import_odb(
                input_file=str(input_file),
                output_dir=str(aedb),
                control_file=None,
                set_as_active=True,
                close_active_project=False,
            )
        elif method == "ipc2581":
            ok = h3d.import_ipc2581(
                input_file=str(input_file),
                output_dir=str(aedb),
                control_file=None,
                set_as_active=True,
                close_active_project=False,
            )
        else:
            raise ValueError(method)
        if ok:
            h3d.save_project(file_name=str(project), overwrite=True)
        return {
            "method": method,
            "input": str(input_file),
            "import_return": bool(ok),
            "project_file": getattr(h3d, "project_file", None),
            "project_name": getattr(h3d, "project_name", None),
            "design_name": getattr(h3d, "design_name", None),
            "design_list": list(getattr(h3d, "design_list", [])),
        }
    finally:
        h3d.release_desktop(close_projects=True, close_desktop=True)


def apply_ports(
    app,
    port_intents: Path,
    method: str = "circuit",
    actual_layers: list[str] | None = None,
    primitive_layers_by_net: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    port_spec = json.loads(port_intents.read_text(encoding="utf-8-sig"))
    unit = str(port_spec.get("unit", "mm"))
    oeditor = app.modeler.oeditor
    existing_ports = list(app.port_list)
    if existing_ports:
        oeditor.Delete(existing_ports)

    created = []
    failures = []
    for port in port_spec.get("ports", []):
        if port.get("type", "circuit") != "circuit":
            failures.append({"port": port.get("name"), "error": f"Unsupported port type: {port.get('type')}"})
            continue
        try:
            before = set(app.port_list)
            positive_x_value = port.get("positive_x")
            positive_y_value = port.get("positive_y")
            negative_x_value = port.get("negative_x")
            negative_y_value = port.get("negative_y")
            if positive_x_value is None or positive_y_value is None:
                raise ValueError(
                    "Circuit port requires explicit positive_x/positive_y on signal copper. "
                    "Legacy x/y fallback is not allowed for HFSS handoff."
                )
            if negative_x_value is None or negative_y_value is None:
                raise ValueError(
                    "Circuit port requires explicit negative_x/negative_y on reference copper. "
                    "Do not pass a single-point or empty-space port to HFSS 3D Layout."
                )
            x = coordinate_to_editor_value(positive_x_value, unit)
            y = coordinate_to_editor_value(positive_y_value, unit)
            x1 = coordinate_to_editor_value(negative_x_value, unit)
            y1 = coordinate_to_editor_value(negative_y_value, unit)
            requested_positive_layer = port.get("positive_layer", port.get("pos_layer"))
            requested_negative_layer = port.get("negative_layer", port.get("neg_layer"))
            if not requested_positive_layer or not requested_negative_layer:
                raise ValueError("Circuit port requires positive_layer and negative_layer.")
            positive_layer_requested = normalize_layout_layer_name(requested_positive_layer, actual_layers)
            net_name = str(port.get("net") or port.get("signal_net") or "")
            positive_layer, signal_layer_matched_intent, primitive_layers_for_net = resolve_signal_layer_from_primitives(
                positive_layer_requested,
                net_name,
                primitive_layers_by_net,
            )
            negative_layer_requested = normalize_layout_layer_name(requested_negative_layer, actual_layers)
            negative_layer = choose_reference_layer_for_signal_layer(
                positive_layer,
                negative_layer_requested,
                actual_layers,
                layer_was_corrected=not signal_layer_matched_intent,
            )
            if method == "pin":
                x_m = coordinate_to_meter(positive_x_value, unit)
                y_m = coordinate_to_meter(positive_y_value, unit)
                app.create_pin_port(
                    name=str(port.get("name")),
                    x=x_m / coordinate_to_meter(1, str(app.modeler.model_units)),
                    y=y_m / coordinate_to_meter(1, str(app.modeler.model_units)),
                    top_layer=positive_layer,
                    bottom_layer=negative_layer,
                )
            else:
                oeditor.CreateCircuitPort(
                    [
                        "NAME:Location",
                        "PosLayer:=",
                        positive_layer,
                        "X0:=",
                        x,
                        "Y0:=",
                        y,
                        "NegLayer:=",
                        negative_layer,
                        "X1:=",
                        x1,
                        "Y1:=",
                        y1,
                    ]
                )
            after = set(app.port_list)
            created_names = sorted(after - before)
            if not created_names:
                raise RuntimeError("CreateCircuitPort returned without adding a port.")
            created.append(
                {
                    "intent_name": port.get("name"),
                    "actual_name": created_names[0],
                    "net": port.get("net") or port.get("signal_net"),
                    "role": port.get("role"),
                    "positive_x": positive_x_value,
                    "positive_y": positive_y_value,
                    "negative_x": negative_x_value,
                    "negative_y": negative_y_value,
                    "requested_positive_layer": requested_positive_layer,
                    "requested_negative_layer": requested_negative_layer,
                    "positive_layer": positive_layer,
                    "negative_layer": negative_layer,
                    "signal_layer_matched_intent": signal_layer_matched_intent,
                    "primitive_layers_for_net": primitive_layers_for_net,
                }
            )
        except Exception as exc:
            failures.append({"port": port.get("name"), "net": port.get("net") or port.get("signal_net"), "error": str(exc)})

    return {
        "source": str(port_intents),
        "method": method,
        "requested_count": len(port_spec.get("ports", [])),
        "created_count": len(created),
        "created": created,
        "failures": failures,
        "actual_layers": actual_layers or [],
        "primitive_layers_by_net": primitive_layers_by_net or {},
        "final_port_list": list(app.port_list),
    }


def reopen_port_count(project: Path, version: str, non_graphical: bool) -> dict[str, object]:
    app = None
    lock = Path(str(project) + ".lock")
    if lock.exists():
        lock.unlink()
    try:
        app = __import__("ansys.aedt.core", fromlist=["Hfss3dLayout"]).Hfss3dLayout(
            project=str(project),
            version=version,
            non_graphical=non_graphical,
            new_desktop=True,
            close_on_exit=False,
        )
        return {
            "design_name": getattr(app, "design_name", None),
            "ports": list(app.port_list),
            "port_count": len(app.port_list),
            "setups": list(app.setup_names),
        }
    finally:
        if app:
            try:
                app.release_desktop(close_projects=True, close_desktop=bool(non_graphical))
            except Exception as exc:
                print(f"WARNING: AEDT reopen release failed: {exc}")


def save_aedt_from_aedb(
    aedb: Path,
    project: Path,
    version: str,
    non_graphical: bool,
    port_intents: Path | None = None,
    port_method: str = "circuit",
    edge_port_type: str = "Gap",
) -> dict[str, object]:
    from ansys.aedt.core import Hfss3dLayout

    project = project.resolve()
    aedb_info = inspect_aedb(aedb, version)
    actual_layers = [str(layer) for layer in aedb_info.get("layers", [])]
    reference_plane_summary = None
    if port_intents:
        reference_plane_summary = ensure_reference_planes_from_port_intents(aedb, port_intents, version, actual_layers)
        aedb_info = inspect_aedb(aedb, version)
        actual_layers = [str(layer) for layer in aedb_info.get("layers", [])]
    primitive_layers_by_net = {
        str(net): [str(layer) for layer in layers]
        for net, layers in dict(aedb_info.get("primitive_layers_by_net", {})).items()
    }
    preopen_port_summary = None
    if port_intents and port_method == "edb_polygon_edge":
        preopen_port_summary = apply_edb_polygon_edge_ports(aedb, port_intents, version)
        if preopen_port_summary["failures"]:
            raise RuntimeError(f"EDB polygon edge port creation failed: {preopen_port_summary['failures'][:3]}")
    elif port_intents and port_method == "edb_path_edge":
        preopen_port_summary = apply_edb_path_edge_ports(
            aedb,
            port_intents,
            version,
            actual_layers=actual_layers,
            primitive_layers_by_net=primitive_layers_by_net,
            edge_port_type=edge_port_type,
        )
        if preopen_port_summary["failures"]:
            raise RuntimeError(f"EDB path edge port creation failed: {preopen_port_summary['failures'][:3]}")

    if preopen_port_summary:
        remove_aedt_shell(project)

    released = False
    h3d = Hfss3dLayout(
        project=str(aedb),
        version=version,
        non_graphical=non_graphical,
        new_desktop=True,
        close_on_exit=False,
    )
    try:
        if preopen_port_summary:
            port_summary = preopen_port_summary
        elif port_intents:
            port_summary = apply_ports(
                h3d,
                port_intents,
                method=port_method,
                actual_layers=actual_layers,
                primitive_layers_by_net=primitive_layers_by_net,
            )
        else:
            port_summary = None
        if port_summary and port_summary["failures"]:
            raise RuntimeError(f"Port creation failed: {port_summary['failures'][:3]}")
        h3d.save_project(file_name=str(project), overwrite=True)
        result = {
            "project_file": getattr(h3d, "project_file", None),
            "project_name": getattr(h3d, "project_name", None),
            "design_name": getattr(h3d, "design_name", None),
            "design_list": list(getattr(h3d, "design_list", [])),
            "aedb_layers_for_port_resolution": actual_layers,
            "primitive_layers_by_net_for_port_resolution": primitive_layers_by_net,
            "reference_plane_repair": reference_plane_summary,
        }
        if port_summary:
            result["ports"] = port_summary
            h3d.release_desktop(close_projects=True, close_desktop=bool(non_graphical))
            released = True
            result["reopen_check"] = reopen_port_count(project, version, non_graphical)
            if result["reopen_check"]["port_count"] != port_summary["created_count"]:
                raise RuntimeError(
                    "Port persistence check failed after reopen: "
                    f"created {port_summary['created_count']}, reopened {result['reopen_check']['port_count']}"
                )
        return result
    finally:
        # The importer opens a new AEDT desktop session. Close non-graphical
        # sessions so repeated harness attempts do not leave orphaned
        # ansysedt.exe gRPC processes. GUI/debug sessions are left open.
        if not released:
            try:
                h3d.release_desktop(close_projects=True, close_desktop=bool(non_graphical))
            except Exception as exc:
                print(f"WARNING: AEDT release failed after save: {exc}")


def write_summary(summary_path: Path, summary: dict[str, object]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    args = parse_args()
    configure_runtime(args.temp_dir)
    odb = Path(args.odb)
    ipc2581 = Path(args.ipc2581) if args.ipc2581 else None
    kicad_board = Path(args.kicad_board) if args.kicad_board else None
    port_intents = Path(args.port_intents) if args.port_intents else None
    project = Path(args.project).resolve()
    summary_path = Path(args.summary).resolve()

    if not odb.exists():
        raise FileNotFoundError(odb)
    if ipc2581 and not ipc2581.exists():
        raise FileNotFoundError(ipc2581)
    if kicad_board and not kicad_board.exists():
        raise FileNotFoundError(kicad_board)
    if port_intents and not port_intents.exists():
        raise FileNotFoundError(port_intents)
    if any(project.with_suffix(suffix).exists() for suffix in [".aedt", ".aedb", ".aedtresults"]) and not args.overwrite:
        raise FileExistsError(f"Project already exists. Pass --overwrite: {project}")
    if args.port_method in {"circuit", "pin"} and not args.allow_coordinate_port_override:
        raise ValueError(
            f"--port-method {args.port_method} is disabled for normal harness runs. "
            "Use --port-method edb_polygon_edge by default, or pass "
            "--allow-coordinate-port-override only for a documented manual/debug experiment."
        )
    if args.port_method == "edb_path_edge" and not args.allow_path_edge_port_override:
        raise ValueError(
            "--port-method edb_path_edge is disabled for normal harness runs. "
            "Use --port-method edb_polygon_edge with endpoint launch pads/tabs. "
            "Pass --allow-path-edge-port-override only for a documented debug "
            "experiment; do not use path-edge output as a valid HFSS/ADS handoff."
        )

    import_input, extracted_from_zip = prepare_odb_input(odb)
    aedb = project.with_suffix(".aedb")

    candidates = []
    if not args.prefer_direct_edb:
        candidates.append(("odb", import_input))
        if odb.suffix.lower() == ".zip":
            candidates.append(("odb", odb))
        if ipc2581:
            candidates.append(("ipc2581", ipc2581))

    attempts = []
    selected = None
    for method, input_file in candidates:
        attempt = import_candidate(method, input_file, project, args.version, args.non_graphical)
        if attempt["import_return"] and aedb.exists():
            attempt["aedb_inspection"] = inspect_aedb(aedb, args.version)
            is_valid = aedb_import_is_valid(attempt["aedb_inspection"], args.min_nets, args.min_layers)
            attempt["nonempty_aedb"] = is_valid
            attempt["aedb_validation"] = "PASS" if is_valid else "FAIL"
            if is_valid:
                selected = attempt
                attempts.append(attempt)
                break
        attempts.append(attempt)
        write_summary(
            summary_path,
            {
                "ok": False,
                "status": "native_import_attempt_failed_validation",
                "aedt_version": args.version,
                "odb": str(odb),
                "ipc2581": str(ipc2581) if ipc2581 else None,
                "kicad_board": str(kicad_board) if kicad_board else None,
                "port_intents": str(port_intents) if port_intents else None,
                "project": str(project),
                "aedb": str(aedb),
                "attempts": attempts,
            },
        )

    if selected is None and (args.direct_edb_fallback or args.prefer_direct_edb) and kicad_board:
        from kicad_board_to_aedb import build_aedb

        remove_project_family(project)
        fallback_summary = build_aedb(kicad_board, aedb, args.version, overwrite=True)
        fallback_inspection = inspect_aedb(aedb, args.version)
        has_content = aedb_import_is_valid(fallback_inspection, args.min_nets, args.min_layers)
        fallback_attempt = {
            "method": "kicad_direct_aedb",
            "input": str(kicad_board),
            "import_return": True,
            "aedb_inspection": fallback_inspection,
            "nonempty_aedb": has_content,
            "aedb_validation": "PASS" if has_content else "FAIL",
            "direct_builder": fallback_summary,
        }
        if has_content:
            fallback_attempt["aedt_save"] = save_aedt_from_aedb(
                aedb,
                project,
                args.version,
                args.non_graphical,
                port_intents=port_intents,
                port_method=args.port_method,
                edge_port_type=args.edge_port_type,
            )
            selected = fallback_attempt
        attempts.append(fallback_attempt)

    if selected is None:
        failed_summary = {
            "ok": False,
            "aedt_version": args.version,
            "odb": str(odb),
            "ipc2581": str(ipc2581) if ipc2581 else None,
            "kicad_board": str(kicad_board) if kicad_board else None,
            "port_intents": str(port_intents) if port_intents else None,
            "import_input": str(import_input),
            "extracted_from_zip": extracted_from_zip,
            "project": str(project),
            "aedb": str(aedb),
            "attempts": attempts,
            "error": "All import candidates returned an empty or invalid AEDB.",
        }
        write_summary(summary_path, failed_summary)
        raise RuntimeError(failed_summary["error"])

    if port_intents and "aedt_save" not in selected:
        selected["aedt_save"] = save_aedt_from_aedb(
            aedb,
            project,
            args.version,
            args.non_graphical,
            port_intents=port_intents,
            port_method=args.port_method,
            edge_port_type=args.edge_port_type,
        )

    summary = {
        "ok": True,
        "aedt_version": args.version,
        "odb": str(odb),
        "ipc2581": str(ipc2581) if ipc2581 else None,
        "kicad_board": str(kicad_board) if kicad_board else None,
        "port_intents": str(port_intents) if port_intents else None,
        "port_method": args.port_method,
        "edge_port_type": args.edge_port_type,
        "import_input": str(import_input),
        "extracted_from_zip": extracted_from_zip,
        "project": str(project),
        "aedb": str(aedb),
        "selected_import": selected,
        "attempts": attempts,
        "non_graphical": args.non_graphical,
    }
    write_summary(summary_path, summary)


if __name__ == "__main__":
    main()
