from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


COPPER_DEFAULT = "copper"
DIELECTRIC_DEFAULT = "FR4_epoxy"


@dataclass
class StackupLayer:
    name: str
    kind: str
    thickness_mm: float
    material: str | None = None
    epsilon_r: float | None = None
    loss_tangent: float | None = None


@dataclass
class Segment:
    start: tuple[float, float]
    end: tuple[float, float]
    width_mm: float
    layer: str
    net_id: int


@dataclass
class Via:
    at: tuple[float, float]
    size_mm: float
    drill_mm: float
    layers: tuple[str, str]
    net_id: int


@dataclass
class Zone:
    layer: str
    net_id: int
    net_name: str
    points: list[tuple[float, float]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a minimal HFSS 3D Layout AEDB directly from a KiCad PCB file."
    )
    parser.add_argument("--board", required=True, help="Input KiCad .kicad_pcb file.")
    parser.add_argument("--aedb", required=True, help="Output .aedb directory.")
    parser.add_argument("--summary", default=None, help="Optional JSON summary path.")
    parser.add_argument("--version", default="2025.1", help="AEDT/PyEDB version, for example 2025.1.")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def sexp_blocks(text: str, head: str) -> list[str]:
    blocks: list[str] = []
    pattern = re.compile(r"\(" + re.escape(head) + r"(?=\s|\))")
    for match in pattern.finditer(text):
        start = match.start()
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start : index + 1])
                    break
    return blocks


def parse_float_pair(block: str, name: str) -> tuple[float, float] | None:
    match = re.search(r"\(" + re.escape(name) + r"\s+([-+0-9.]+)\s+([-+0-9.]+)\)", block)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def parse_nets(text: str) -> dict[int, str]:
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', text)
        if int(match.group(1)) != 0
    }


def parse_stackup(text: str) -> list[StackupLayer]:
    setup_blocks = sexp_blocks(text, "setup")
    stackup_text = ""
    if setup_blocks:
        stackup_blocks = sexp_blocks(setup_blocks[0], "stackup")
        stackup_text = stackup_blocks[0] if stackup_blocks else ""
    layers: list[StackupLayer] = []
    for block in sexp_blocks(stackup_text, "layer"):
        name_match = re.match(r'\(layer\s+"([^"]+)"', block)
        type_match = re.search(r'\(type\s+"?([^"\)\s]+)"?\)', block)
        thickness_match = re.search(r"\(thickness\s+([-+0-9.]+)\)", block)
        material_match = re.search(r'\(material\s+"([^"]+)"\)', block)
        eps_match = re.search(r"\(epsilon_r\s+([-+0-9.]+)\)", block)
        loss_match = re.search(r"\(loss_tangent\s+([-+0-9.]+)\)", block)
        if not name_match:
            continue
        layers.append(
            StackupLayer(
                name=name_match.group(1),
                kind=(type_match.group(1) if type_match else "copper").lower(),
                thickness_mm=float(thickness_match.group(1)) if thickness_match else 0.035,
                material=material_match.group(1) if material_match else None,
                epsilon_r=float(eps_match.group(1)) if eps_match else None,
                loss_tangent=float(loss_match.group(1)) if loss_match else None,
            )
        )
    if layers:
        return layers
    board_layers = sexp_blocks(text, "layers")
    if not board_layers:
        return []
    for match in re.finditer(r'\(\d+\s+"([^"]+)"\s+([a-zA-Z.]+)', board_layers[0]):
        name = match.group(1)
        kind = "copper" if name.endswith(".Cu") else "dielectric"
        layers.append(StackupLayer(name=name, kind=kind, thickness_mm=0.035))
    return [layer for layer in layers if layer.name.endswith(".Cu")]


def parse_segments(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for block in sexp_blocks(text, "segment"):
        start = parse_float_pair(block, "start")
        end = parse_float_pair(block, "end")
        width_match = re.search(r"\(width\s+([-+0-9.]+)\)", block)
        layer_match = re.search(r'\(layer\s+"([^"]+)"\)', block)
        net_match = re.search(r"\(net\s+(\d+)\)", block)
        if not (start and end and width_match and layer_match and net_match):
            continue
        segments.append(
            Segment(
                start=start,
                end=end,
                width_mm=float(width_match.group(1)),
                layer=layer_match.group(1),
                net_id=int(net_match.group(1)),
            )
        )
    return segments


def parse_vias(text: str) -> list[Via]:
    vias: list[Via] = []
    for block in sexp_blocks(text, "via"):
        at = parse_float_pair(block, "at")
        size_match = re.search(r"\(size\s+([-+0-9.]+)\)", block)
        drill_match = re.search(r"\(drill\s+([-+0-9.]+)\)", block)
        layers_match = re.search(r'\(layers\s+"([^"]+)"\s+"([^"]+)"\)', block)
        net_match = re.search(r"\(net\s+(\d+)\)", block)
        if not (at and size_match and drill_match and layers_match and net_match):
            continue
        vias.append(
            Via(
                at=at,
                size_mm=float(size_match.group(1)),
                drill_mm=float(drill_match.group(1)),
                layers=(layers_match.group(1), layers_match.group(2)),
                net_id=int(net_match.group(1)),
            )
        )
    return vias


def parse_zones(text: str) -> list[Zone]:
    zones: list[Zone] = []
    for block in sexp_blocks(text, "zone"):
        layer_match = re.search(r'\(layer\s+"([^"]+)"\)', block)
        net_match = re.search(r"\(net\s+(\d+)\)", block)
        net_name_match = re.search(r'\(net_name\s+"([^"]+)"\)', block)
        points = [
            (float(match.group(1)), float(match.group(2)))
            for match in re.finditer(r"\(xy\s+([-+0-9.]+)\s+([-+0-9.]+)\)", block)
        ]
        if not (layer_match and net_match and points):
            continue
        zones.append(
            Zone(
                layer=layer_match.group(1),
                net_id=int(net_match.group(1)),
                net_name=net_name_match.group(1) if net_name_match else "",
                points=points,
            )
        )
    return zones


def parse_edge_bbox(text: str) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []
    for block in sexp_blocks(text, "gr_line"):
        if '(layer "Edge.Cuts")' not in block:
            continue
        for name in ("start", "end"):
            point = parse_float_pair(block, name)
            if point:
                points.append(point)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def ensure_materials(edb, layers: list[StackupLayer]) -> None:
    try:
        edb.materials.add_conductor_material(COPPER_DEFAULT, conductivity=58000000)
    except Exception:
        pass
    for layer in layers:
        if layer.kind == "copper":
            continue
        name = layer.material or DIELECTRIC_DEFAULT
        if name == DIELECTRIC_DEFAULT:
            continue
        try:
            edb.materials.add_dielectric_material(
                name,
                permittivity=layer.epsilon_r or 4.0,
                dielectric_loss_tangent=layer.loss_tangent or 0.02,
            )
        except Exception:
            pass


def mm(value: float) -> str:
    return f"{value:.9g}mm"


def add_stackup(edb, layers: list[StackupLayer]) -> None:
    if not layers:
        raise ValueError("No KiCad stackup layers found.")
    default_fill = next(
        (layer.material for layer in layers if layer.kind != "copper" and layer.material),
        DIELECTRIC_DEFAULT,
    )
    for index, layer in enumerate(layers):
        is_copper = layer.kind == "copper" or layer.name.endswith(".Cu")
        layer_type = "signal" if is_copper else "dielectric"
        material = COPPER_DEFAULT if is_copper else (layer.material or DIELECTRIC_DEFAULT)
        kwargs = {
            "layer_name": layer.name,
            "layer_type": layer_type,
            "material": material,
            "thickness": mm(layer.thickness_mm),
        }
        if is_copper:
            kwargs["fillMaterial"] = default_fill
        else:
            kwargs["fillMaterial"] = material
        if index == 0:
            edb.stackup.add_layer(**kwargs)
        else:
            edb.stackup.add_layer(method="add_on_bottom", **kwargs)


def point_key(point: tuple[float, float]) -> tuple[float, float]:
    return round(point[0], 6), round(point[1], 6)


def build_trace_paths(segments: list[Segment], nets: dict[int, str]) -> list[dict[str, object]]:
    paths: list[dict[str, object]] = []
    groups: dict[tuple[int, str, float], list[Segment]] = {}
    for segment in segments:
        if not nets.get(segment.net_id, ""):
            continue
        groups.setdefault((segment.net_id, segment.layer, round(segment.width_mm, 9)), []).append(segment)

    for (net_id, layer, width), group in groups.items():
        unused = set(range(len(group)))
        adjacency: dict[tuple[float, float], list[tuple[tuple[float, float], int]]] = {}
        for idx, segment in enumerate(group):
            a = point_key(segment.start)
            b = point_key(segment.end)
            adjacency.setdefault(a, []).append((b, idx))
            adjacency.setdefault(b, []).append((a, idx))

        while unused:
            endpoints = [point for point, edges in adjacency.items() if any(edge_idx in unused for _other, edge_idx in edges) and len(edges) == 1]
            start = endpoints[0] if endpoints else point_key(group[next(iter(unused))].start)
            ordered = [start]
            current = start
            previous = None
            while True:
                next_item = None
                for neighbor, edge_idx in adjacency.get(current, []):
                    if edge_idx in unused and neighbor != previous:
                        next_item = (neighbor, edge_idx)
                        break
                if next_item is None:
                    break
                neighbor, edge_idx = next_item
                unused.remove(edge_idx)
                ordered.append(neighbor)
                previous, current = current, neighbor

            paths.append(
                {
                    "net_name": nets.get(net_id, ""),
                    "layer": layer,
                    "width_mm": float(width),
                    "points": ordered,
                }
            )
    return paths


def line_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> tuple[float, float] | None:
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
    return px, py


def polyline_outline(points: list[tuple[float, float]], width_mm: float) -> list[tuple[float, float]]:
    """Return a simple mitered copper polygon around a centerline polyline."""
    if len(points) < 2:
        return []
    half = width_mm / 2.0
    normals: list[tuple[float, float]] = []
    for a, b in zip(points, points[1:]):
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        length = (dx * dx + dy * dy) ** 0.5
        if length <= 1e-12:
            normals.append((0.0, 0.0))
        else:
            normals.append((-dy / length * half, dx / length * half))

    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for idx, point in enumerate(points):
        if idx == 0:
            nx, ny = normals[0]
            left.append((point[0] + nx, point[1] + ny))
            right.append((point[0] - nx, point[1] - ny))
        elif idx == len(points) - 1:
            nx, ny = normals[-1]
            left.append((point[0] + nx, point[1] + ny))
            right.append((point[0] - nx, point[1] - ny))
        else:
            prev_n = normals[idx - 1]
            next_n = normals[idx]
            prev_a = (points[idx - 1][0] + prev_n[0], points[idx - 1][1] + prev_n[1])
            prev_b = (point[0] + prev_n[0], point[1] + prev_n[1])
            next_a = (point[0] + next_n[0], point[1] + next_n[1])
            next_b = (points[idx + 1][0] + next_n[0], points[idx + 1][1] + next_n[1])
            left.append(line_intersection(prev_a, prev_b, next_a, next_b) or next_a)

            prev_a = (points[idx - 1][0] - prev_n[0], points[idx - 1][1] - prev_n[1])
            prev_b = (point[0] - prev_n[0], point[1] - prev_n[1])
            next_a = (point[0] - next_n[0], point[1] - next_n[1])
            next_b = (points[idx + 1][0] - next_n[0], points[idx + 1][1] - next_n[1])
            right.append(line_intersection(prev_a, prev_b, next_a, next_b) or next_a)
    return left + list(reversed(right))


def segment_outline(start: tuple[float, float], end: tuple[float, float], width_mm: float) -> list[tuple[float, float]]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1e-12:
        half = width_mm / 2.0
        return [
            (start[0] - half, start[1] - half),
            (start[0] + half, start[1] - half),
            (start[0] + half, start[1] + half),
            (start[0] - half, start[1] + half),
        ]
    nx = -dy / length * width_mm / 2.0
    ny = dx / length * width_mm / 2.0
    return [
        (start[0] + nx, start[1] + ny),
        (end[0] + nx, end[1] + ny),
        (end[0] - nx, end[1] - ny),
        (start[0] - nx, start[1] - ny),
    ]


def add_vias(edb, nets: dict[int, str], vias: list[Via]) -> int:
    via_count = 0
    definitions: dict[tuple[float, float, str, str], str] = {}
    for via in vias:
        net_name = nets.get(via.net_id, "")
        if not net_name:
            continue
        start_layer, stop_layer = via.layers
        key = (round(via.size_mm, 6), round(via.drill_mm, 6), start_layer, stop_layer)
        padstack_name = definitions.get(key)
        if padstack_name is None:
            padstack_name = f"SIPI_VIA_{len(definitions) + 1}_{start_layer.replace('.', '')}_{stop_layer.replace('.', '')}"
            antipad = max(via.size_mm + 0.025, via.drill_mm + 0.035)
            edb.padstacks.create(
                padstackname=padstack_name,
                holediam=mm(via.drill_mm),
                paddiam=mm(via.size_mm),
                antipaddiam=mm(antipad),
                start_layer=start_layer,
                stop_layer=stop_layer,
            )
            definitions[key] = padstack_name
        edb.padstacks.place(
            position=[via.at[0] * 1e-3, via.at[1] * 1e-3],
            definition_name=padstack_name,
            net_name=net_name,
            via_name=f"via_{net_name}_{via_count}",
            fromlayer=start_layer,
            tolayer=stop_layer,
        )
        via_count += 1
    return via_count


def add_geometry(edb, nets: dict[int, str], segments: list[Segment], vias: list[Via], zones: list[Zone], bbox) -> dict[str, int]:
    zone_count = 0
    trace_count = 0
    launch_pad_count = 0
    for zone in zones:
        net_name = zone.net_name or nets.get(zone.net_id, "")
        if not net_name:
            continue
        edb.modeler.create_polygon(
            points=[[mm(point[0]), mm(point[1])] for point in zone.points],
            layer_name=zone.layer,
            net_name=net_name,
        )
        zone_count += 1

    if not zones and bbox:
        min_x, min_y, max_x, max_y = bbox
        margin = 0.5
        for layer_name in [name for name in edb.stackup.layers if str(name).endswith(".Cu")]:
            if layer_name == "F.Cu":
                continue
            edb.modeler.create_rectangle(
                layer_name=str(layer_name),
                net_name="GND",
                lower_left_point=[mm(min_x + margin), mm(min_y + margin)],
                upper_right_point=[mm(max_x - margin), mm(max_y - margin)],
            )
            zone_count += 1

    trace_paths = build_trace_paths(segments, nets)
    for segment in segments:
        net_name = nets.get(segment.net_id, "")
        if not net_name:
            continue
        outline = segment_outline(segment.start, segment.end, segment.width_mm)
        edb.modeler.create_polygon(
            points=[[mm(point[0]), mm(point[1])] for point in outline],
            layer_name=str(segment.layer),
            net_name=str(net_name),
        )
        trace_count += 1

    launch_points: dict[tuple[str, str, float, float], float] = {}
    endpoint_counts: dict[tuple[str, str, float, float], int] = {}
    for trace_path in trace_paths:
        points = trace_path["points"]
        if len(points) < 2:
            continue
        for point_index, point in enumerate(points):
            key = (
                str(trace_path["layer"]),
                str(trace_path["net_name"]),
                round(point[0], 6),
                round(point[1], 6),
            )
            launch_points[key] = max(launch_points.get(key, 0.0), float(trace_path["width_mm"]))
            endpoint_counts[key] = 1 if point_index in {0, len(points) - 1} else 2

    # Only create endpoint launch pads at open trace ends. For routed polylines,
    # bend points occur as the end of one segment and the start of the next; adding
    # extra rectangular pads there changes coupling and impedance artificially.
    junction_points = {key: width for key, width in launch_points.items() if endpoint_counts.get(key, 0) > 1}
    launch_points = {key: width for key, width in launch_points.items() if endpoint_counts.get(key, 0) == 1}

    nearest_launch_spacing_by_layer: dict[str, float] = {}
    points_by_layer: dict[str, list[tuple[float, float]]] = {}
    for layer_name, _net_name, x, y in launch_points:
        points_by_layer.setdefault(layer_name, []).append((x, y))
    for layer_name, points in points_by_layer.items():
        nearest = None
        for idx, point_a in enumerate(points):
            for point_b in points[idx + 1 :]:
                distance = ((point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2) ** 0.5
                if distance <= 1e-9:
                    continue
                nearest = distance if nearest is None else min(nearest, distance)
        if nearest is not None:
            nearest_launch_spacing_by_layer[layer_name] = nearest

    launch_pad_sizes: list[float] = []
    for (layer_name, net_name, x, y), width in launch_points.items():
        # Keep fallback launch geometry local to each trace. Dense package channels can
        # have pitch barely larger than trace width; oversized endpoint pads short or
        # merge adjacent port regions and produce open-like HFSS multiport results.
        pad_size = max(width * 1.05, 0.020)
        nearest_spacing = nearest_launch_spacing_by_layer.get(layer_name)
        if nearest_spacing is not None:
            pad_size = min(pad_size, nearest_spacing * 0.80)
        launch_pad_sizes.append(pad_size)
        half = pad_size / 2.0
        edb.modeler.create_rectangle(
            layer_name=layer_name,
            net_name=net_name,
            lower_left_point=[mm(x - half), mm(y - half)],
            upper_right_point=[mm(x + half), mm(y + half)],
        )
        launch_pad_count += 1

    junction_pad_count = 0
    for (layer_name, net_name, x, y), width in junction_points.items():
        pad_size = max(width * 1.10, 0.020)
        nearest_spacing = nearest_launch_spacing_by_layer.get(layer_name)
        if nearest_spacing is not None:
            pad_size = min(pad_size, nearest_spacing * 0.80)
        half = pad_size / 2.0
        edb.modeler.create_rectangle(
            layer_name=layer_name,
            net_name=net_name,
            lower_left_point=[mm(x - half), mm(y - half)],
            upper_right_point=[mm(x + half), mm(y + half)],
        )
        junction_pad_count += 1

    via_count = add_vias(edb, nets, vias)

    return {
        "zones": zone_count,
        "traces": trace_count,
        "vias": via_count,
        "launch_pads": launch_pad_count,
        "junction_pads": junction_pad_count,
        "launch_pad_size_min_mm": min(launch_pad_sizes) if launch_pad_sizes else None,
        "launch_pad_size_max_mm": max(launch_pad_sizes) if launch_pad_sizes else None,
        "nearest_launch_spacing_by_layer_mm": nearest_launch_spacing_by_layer,
    }


def names_from_mapping_or_list(value) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return sorted(str(item) for item in value)


def inspect_aedb(edb) -> dict[str, object]:
    nets = names_from_mapping_or_list(edb.nets.nets)
    layers = names_from_mapping_or_list(edb.stackup.layers)
    component_source = getattr(edb.components, "components", None)
    if component_source is None:
        component_source = getattr(edb.components, "instances", {})
    components = names_from_mapping_or_list(component_source)
    return {
        "net_count": len(nets),
        "nets": nets,
        "layer_count": len(layers),
        "layers": layers,
        "component_count": len(components),
        "components": components,
    }


def build_aedb(board: Path, aedb: Path, version: str, overwrite: bool) -> dict[str, object]:
    try:
        from pyedb.generic.settings import settings as pyedb_settings

        pyedb_settings.enable_global_log_file = True
        pyedb_settings.enable_local_log_file = False
        pyedb_settings.global_log_file_name = str(aedb.with_suffix(".pyedb.log"))
    except Exception:
        pass
    from pyedb import Edb

    if aedb.exists():
        if not overwrite:
            raise FileExistsError(f"AEDB already exists. Pass --overwrite: {aedb}")
        shutil.rmtree(aedb)

    text = board.read_text(encoding="utf8")
    nets = parse_nets(text)
    layers = parse_stackup(text)
    segments = parse_segments(text)
    vias = parse_vias(text)
    zones = parse_zones(text)
    bbox = parse_edge_bbox(text)

    edb = Edb(edbpath=str(aedb), version=version)
    try:
        ensure_materials(edb, layers)
        add_stackup(edb, layers)
        created = add_geometry(edb, nets, segments, vias, zones, bbox)
        inspection = inspect_aedb(edb)
        if hasattr(edb, "save_edb"):
            edb.save_edb()
        else:
            edb.save()
    finally:
        edb.close()

    return {
        "ok": True,
        "board": str(board),
        "aedb": str(aedb),
        "aedt_version": version,
        "parsed": {
            "nets": len(nets),
            "stackup_layers": len(layers),
            "segments": len(segments),
            "vias": len(vias),
            "zones": len(zones),
            "edge_bbox_mm": bbox,
        },
        "created": created,
        "aedb_inspection": inspection,
        "limitations": [
            "Fallback preserves stackup, zones, and routed track segments; it is not a full KiCad-to-EDB replacement.",
            "Use native ODB++/IPC-2581 import when it validates as non-empty.",
            "Complex footprint metal and arcs are intentionally outside this minimal fallback.",
        ],
    }


def main() -> None:
    args = parse_args()
    board = Path(args.board)
    aedb = Path(args.aedb)
    if not board.exists():
        raise FileNotFoundError(board)
    summary = build_aedb(board, aedb, args.version, args.overwrite)
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
