from __future__ import annotations

import argparse
import heapq
import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def kid() -> str:
    return str(uuid.uuid4())


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "channel_case"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a generic multi-lane PCB/package channel case with deterministic A* routing."
    )
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--interface", default="generic_high_speed_channel")
    parser.add_argument("--package-class", default="generic_package")
    parser.add_argument("--lane-count", type=int, default=8)
    parser.add_argument("--data-rate-gbps", type=float, default=None)
    parser.add_argument("--channel-length-mm", type=float, required=True)
    parser.add_argument("--layer-count", type=int, default=4)
    parser.add_argument("--dk", type=float, default=4.3)
    parser.add_argument("--df", type=float, default=0.01)
    parser.add_argument("--bump-pitch-um", type=float, default=None)
    parser.add_argument("--bump-pitch-mm", type=float, default=None)
    parser.add_argument("--columns", type=int, default=None)
    parser.add_argument("--trace-width-mm", type=float, default=None)
    parser.add_argument("--clearance-mm", type=float, default=None)
    parser.add_argument("--target-impedance-ohm", type=float, default=50.0)
    parser.add_argument("--grid-mm", type=float, default=None)
    parser.add_argument("--endpoint-map", type=Path, default=None)
    parser.add_argument("--strategy", type=Path, default=None)
    parser.add_argument("--spec-evidence", type=Path, default=None)
    parser.add_argument("--source-status", default="synthetic_or_unreviewed")
    parser.add_argument(
        "--allow-proxy-fanout-endpoints",
        action="store_true",
        help=(
            "Allow a spec/table/figure endpoint map that records source bump/ball/pin "
            "coordinates but routes from simplified fanout launch coordinates. This is "
            "blocked by default because it can collapse a real bump map into straight "
            "parallel lines and create invalid HFSS port launches."
        ),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


@dataclass
class Endpoint:
    name: str
    tx: tuple[float, float]
    rx: tuple[float, float]
    layer: str


def rounded(value: float) -> float:
    return round(float(value), 6)


def choose_width_and_clearance(pitch_mm: float, width: float | None, clearance: float | None) -> tuple[float, float]:
    if width is None:
        width = min(0.040, max(0.015, pitch_mm * 0.30))
    if clearance is None:
        clearance = min(max(0.015, width * 0.75), max(0.010, pitch_mm - width))
    if width + clearance >= pitch_mm:
        width = max(0.010, pitch_mm * 0.35)
        clearance = max(0.006, pitch_mm * 0.25)
    return rounded(width), rounded(clearance)


def load_endpoint_map(path: Path) -> tuple[list[Endpoint], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    lanes = []
    for idx, lane in enumerate(payload.get("lanes", [])):
        name = str(lane.get("name") or lane.get("net") or f"DATA{idx:02d}")
        tx = lane.get("tx") or lane.get("start")
        rx = lane.get("rx") or lane.get("end")
        if not tx or not rx:
            raise ValueError(f"Endpoint lane {name} needs tx/rx or start/end coordinates.")
        layer = str(lane.get("layer") or tx.get("layer") or rx.get("layer") or "F.Cu")
        lanes.append(
            Endpoint(
                name=name,
                tx=(float(tx["x"]), float(tx["y"])),
                rx=(float(rx["x"]), float(rx["y"])),
                layer=layer,
            )
        )
    if not lanes:
        raise ValueError(f"Endpoint map has no lanes: {path}")
    return lanes, payload


def text_contains_proxy(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            token in lowered
            for token in (
                "proxy",
                "synthetic",
                "fanout_escape",
                "escape launch",
                "not raw bump",
                "not raw ball",
                "not raw pin",
                "simplified",
            )
        )
    if isinstance(value, list):
        return any(text_contains_proxy(item) for item in value)
    if isinstance(value, dict):
        return any(text_contains_proxy(item) for item in value.values())
    return False


def endpoint_map_uses_source_map(payload: dict[str, Any]) -> bool:
    source_type = str(payload.get("source_type") or "").lower()
    if any(token in source_type for token in ("spec", "figure", "table", "bump", "ball", "pin")):
        return True
    for lane in payload.get("lanes", []):
        if any(
            key in lane
            for key in (
                "source_tx_bump",
                "source_rx_bump",
                "source_tx_ball",
                "source_rx_ball",
                "source_tx_pin",
                "source_rx_pin",
            )
        ):
            return True
    return False


def validate_endpoint_map_for_routing(payload: dict[str, Any], allow_proxy_fanout: bool) -> dict[str, Any]:
    """Reject endpoint maps that keep spec-map evidence but route from proxy launches.

    The generator may be used for generic synthetic exploration, but when an
    endpoint map says it came from a governing spec figure/table and then records
    that actual geometry is a proxy/fanout escape, the layout must not silently
    proceed to KiCad/HFSS as if it were the real package map.
    """
    uses_source_map = endpoint_map_uses_source_map(payload)
    proxy_marked = text_contains_proxy(
        {
            "source_status": payload.get("source_status"),
            "reviewer_status": payload.get("reviewer_status"),
            "compliance_status": payload.get("compliance_status"),
            "coordinate_basis": payload.get("coordinate_basis"),
            "evidence_to_geometry_audit": payload.get("evidence_to_geometry_audit"),
            "notes": payload.get("notes"),
        }
    )
    result = {
        "uses_source_map": uses_source_map,
        "proxy_or_fanout_escape_marked": proxy_marked,
        "allow_proxy_fanout_endpoints": allow_proxy_fanout,
    }
    if uses_source_map and proxy_marked and not allow_proxy_fanout:
        raise RuntimeError(
            "Endpoint map contains spec/table/figure-derived bump/ball/pin evidence but "
            "routes from proxy or fanout-escape launch coordinates. Use a bump-to-bump/"
            "pin-to-pin router that preserves the extracted map, or rerun with "
            "--allow-proxy-fanout-endpoints only for an explicitly blocked/proxy study "
            "that will not proceed as a valid HFSS/ADS compliance candidate."
        )
    return result


def synthetic_endpoint_map(
    lane_count: int,
    pitch_mm: float,
    channel_length_mm: float,
    columns: int | None,
    margin_x_mm: float,
    margin_y_mm: float,
) -> tuple[list[Endpoint], dict[str, Any]]:
    columns = columns or min(max(lane_count, 1), 8)
    rows = math.ceil(lane_count / columns)
    endpoints: list[Endpoint] = []
    for lane in range(lane_count):
        col = lane % columns
        row = lane // columns
        y = margin_y_mm + row * pitch_mm * 1.8 + col * pitch_mm
        endpoints.append(
            Endpoint(
                name=f"DATA{lane:02d}",
                tx=(margin_x_mm, y),
                rx=(margin_x_mm + channel_length_mm, y),
                layer="F.Cu",
            )
        )
    payload = {
        "source_type": "synthetic",
        "source_status": "proxy_until_spec_or_user_endpoint_map_is_reviewed",
        "lane_count": lane_count,
        "columns": columns,
        "rows": rows,
        "bump_pitch_mm": pitch_mm,
        "lane_order": [endpoint.name for endpoint in endpoints],
        "notes": [
            "Generated because no reviewed endpoint/bump/ball/pin map was supplied to the generic generator.",
            "Compliance remains blocked until endpoint placement is tied to reviewed tier-0 or user-approved evidence.",
        ],
    }
    payload["lanes"] = [
        {
            "name": endpoint.name,
            "tx": {"x": endpoint.tx[0], "y": endpoint.tx[1], "layer": endpoint.layer},
            "rx": {"x": endpoint.rx[0], "y": endpoint.rx[1], "layer": endpoint.layer},
        }
        for endpoint in endpoints
    ]
    return endpoints, payload


def grid_key(point: tuple[float, float], grid: float) -> tuple[int, int]:
    return int(round(point[0] / grid)), int(round(point[1] / grid))


def grid_point(key: tuple[int, int], grid: float) -> tuple[float, float]:
    return key[0] * grid, key[1] * grid


def segment_distance_to_point(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    if length2 <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def point_too_close_to_paths(
    point: tuple[float, float],
    accepted_paths: list[list[tuple[float, float]]],
    keepout_mm: float,
) -> bool:
    for path in accepted_paths:
        for start, end in zip(path, path[1:]):
            if segment_distance_to_point(start, end, point) < keepout_mm:
                return True
    return False


def astar_route(
    start: tuple[float, float],
    goal: tuple[float, float],
    grid: float,
    bounds: tuple[float, float, float, float],
    keepout_paths: list[list[tuple[float, float]]],
    keepout_mm: float,
) -> list[tuple[float, float]]:
    start_key = grid_key(start, grid)
    goal_key = grid_key(goal, grid)
    x0, y0, x1, y1 = bounds
    min_key = grid_key((x0, y0), grid)
    max_key = grid_key((x1, y1), grid)
    moves = [
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, math.sqrt(2)),
        (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)),
        (1, 1, math.sqrt(2)),
    ]

    def heuristic(key: tuple[int, int]) -> float:
        dx = abs(key[0] - goal_key[0])
        dy = abs(key[1] - goal_key[1])
        return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)

    frontier: list[tuple[float, tuple[int, int]]] = [(heuristic(start_key), start_key)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_key: None}
    cost_so_far: dict[tuple[int, int], float] = {start_key: 0.0}

    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal_key:
            break
        for dx, dy, move_cost in moves:
            nxt = (current[0] + dx, current[1] + dy)
            if nxt[0] < min_key[0] or nxt[0] > max_key[0] or nxt[1] < min_key[1] or nxt[1] > max_key[1]:
                continue
            if dx and dy:
                # Prevent corner cutting through inflated keepouts.
                p1 = grid_point((current[0] + dx, current[1]), grid)
                p2 = grid_point((current[0], current[1] + dy), grid)
                if point_too_close_to_paths(p1, keepout_paths, keepout_mm) or point_too_close_to_paths(
                    p2, keepout_paths, keepout_mm
                ):
                    continue
            point = grid_point(nxt, grid)
            if nxt not in {start_key, goal_key} and point_too_close_to_paths(point, keepout_paths, keepout_mm):
                continue
            new_cost = cost_so_far[current] + move_cost
            if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                cost_so_far[nxt] = new_cost
                heapq.heappush(frontier, (new_cost + heuristic(nxt), nxt))
                came_from[nxt] = current

    if goal_key not in came_from:
        raise RuntimeError(f"A* could not route from {start} to {goal} under current keepouts.")
    keys = []
    current: tuple[int, int] | None = goal_key
    while current is not None:
        keys.append(current)
        current = came_from[current]
    keys.reverse()
    points = [grid_point(key, grid) for key in keys]
    points[0] = start
    points[-1] = goal
    return compress_collinear(points)


def compress_collinear(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return [(rounded(x), rounded(y)) for x, y in points]
    compressed = [points[0]]
    prev_dir = None
    for a, b in zip(points, points[1:]):
        dx = round((b[0] - a[0]), 9)
        dy = round((b[1] - a[1]), 9)
        length = math.hypot(dx, dy)
        direction = (round(dx / length, 6), round(dy / length, 6)) if length else (0.0, 0.0)
        if prev_dir is not None and direction != prev_dir:
            compressed.append(a)
        prev_dir = direction
    compressed.append(points[-1])
    return [(rounded(x), rounded(y)) for x, y in compressed]


def path_length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def kicad_project(case_name: str) -> str:
    return json.dumps(
        {
            "meta": {"filename": f"{case_name}.kicad_pro", "version": 1},
            "board": {"design_settings": {"defaults": {"board_outline_line_width": 0.1}}},
        },
        indent=2,
    )


def stackup_block(layer_count: int, dk: float, df: float) -> tuple[str, list[str], str]:
    if layer_count >= 4:
        board_layers = [
            '\t\t(0 "F.Cu" signal)',
            '\t\t(1 "In1.Cu" signal)',
            '\t\t(2 "In2.Cu" signal)',
            '\t\t(31 "B.Cu" signal)',
        ]
        stackup = f"""
\t\t(stackup
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.018))
\t\t\t(layer "dielectric 1" (type "core") (thickness 0.080) (material "organic") (epsilon_r {dk}) (loss_tangent {df}))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.018))
\t\t\t(layer "dielectric 2" (type "core") (thickness 0.100) (material "organic") (epsilon_r {dk}) (loss_tangent {df}))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.018))
\t\t\t(layer "dielectric 3" (type "core") (thickness 0.080) (material "organic") (epsilon_r {dk}) (loss_tangent {df}))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.018))
\t\t)
"""
        return "\n".join(board_layers), ["In1.Cu", "In2.Cu"], stackup
    board_layers = ['\t\t(0 "F.Cu" signal)', '\t\t(31 "B.Cu" signal)']
    stackup = f"""
\t\t(stackup
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.018))
\t\t\t(layer "dielectric 1" (type "core") (thickness 0.160) (material "organic") (epsilon_r {dk}) (loss_tangent {df}))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.018))
\t\t)
"""
    return "\n".join(board_layers), ["B.Cu"], stackup


def zone_block(net_id: int, net_name: str, layer: str, x0: float, y0: float, x1: float, y1: float) -> str:
    return f"""
\t(zone
\t\t(net {net_id})
\t\t(net_name "{net_name}")
\t\t(layer "{layer}")
\t\t(uuid "{kid()}")
\t\t(hatch edge 0.5)
\t\t(connect_pads (clearance 0.025))
\t\t(min_thickness 0.010)
\t\t(filled_areas_thickness no)
\t\t(fill yes (thermal_gap 0.05) (thermal_bridge_width 0.05))
\t\t(polygon
\t\t\t(pts
\t\t\t\t(xy {x0:.6f} {y0:.6f})
\t\t\t\t(xy {x1:.6f} {y0:.6f})
\t\t\t\t(xy {x1:.6f} {y1:.6f})
\t\t\t\t(xy {x0:.6f} {y1:.6f})
\t\t\t)
\t\t)
\t)
"""


def write_kicad_board(
    path: Path,
    case_name: str,
    endpoints: list[Endpoint],
    routes: list[dict[str, Any]],
    width_mm: float,
    height_mm: float,
    trace_width_mm: float,
    launch_width_mm: float,
    layer_count: int,
    dk: float,
    df: float,
) -> None:
    board_layers, reference_layers, stackup = stackup_block(layer_count, dk, df)
    extra_user_layers = """
\t\t(32 "B.Adhes" user)
\t\t(33 "F.Adhes" user)
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user)
\t\t(37 "F.SilkS" user)
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(44 "Edge.Cuts" user)
"""
    net_lines = ['\t(net 0 "")', '\t(net 1 "GND")']
    net_ids = {"GND": 1}
    for index, endpoint in enumerate(endpoints, start=2):
        net_ids[endpoint.name] = index
        net_lines.append(f'\t(net {index} "{endpoint.name}")')

    edge = [
        f'\t(gr_line (start 0 0) (end {width_mm:.6f} 0) (stroke (width 0.050) (type default)) (layer "Edge.Cuts") (uuid "{kid()}"))',
        f'\t(gr_line (start {width_mm:.6f} 0) (end {width_mm:.6f} {height_mm:.6f}) (stroke (width 0.050) (type default)) (layer "Edge.Cuts") (uuid "{kid()}"))',
        f'\t(gr_line (start {width_mm:.6f} {height_mm:.6f}) (end 0 {height_mm:.6f}) (stroke (width 0.050) (type default)) (layer "Edge.Cuts") (uuid "{kid()}"))',
        f'\t(gr_line (start 0 {height_mm:.6f}) (end 0 0) (stroke (width 0.050) (type default)) (layer "Edge.Cuts") (uuid "{kid()}"))',
    ]
    zones = [
        zone_block(1, "GND", layer, 0.25, 0.25, width_mm - 0.25, height_mm - 0.25)
        for layer in reference_layers
    ]
    segments: list[str] = []
    for route in routes:
        net_id = net_ids[route["net"]]
        layer = route["layer"]
        points = route["points"]
        for idx, (start, end) in enumerate(zip(points, points[1:])):
            seg_width = trace_width_mm
            segments.append(
                f'\t(segment (start {start[0]:.6f} {start[1]:.6f}) (end {end[0]:.6f} {end[1]:.6f}) '
                f'(width {seg_width:.6f}) (layer "{layer}") (net {net_id}) (uuid "{kid()}"))'
            )

    text = f"""(kicad_pcb
\t(version 20241229)
\t(generator "sipi-harness-generic-channel")
\t(generator_version "0.1")
\t(general (thickness 0.252))
\t(paper "A4")
\t(layers
{board_layers}
{extra_user_layers}\t)
\t(setup
{stackup}\t)
{chr(10).join(net_lines)}
{chr(10).join(edge)}
{chr(10).join(zones)}
{chr(10).join(segments)}
\t(gr_text "Generic channel candidate: {case_name}"
\t\t(at 0.5 {max(0.5, height_mm - 0.4):.6f} 0)
\t\t(layer "F.SilkS")
\t\t(effects (font (size 0.35 0.35) (thickness 0.05)))
\t\t(uuid "{kid()}")
\t)
)
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    case_dir = args.case_dir.resolve()
    case_name = safe_name(args.case_name or case_dir.name)
    if args.layer_count not in {2, 4}:
        raise ValueError(
            "create_generic_channel_case currently supports 2-layer and 4-layer candidates only. "
            "For other stackups, provide a reviewed stackup-specific generator or extend stackup_block()."
        )
    if case_dir.exists() and any(case_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Case directory exists and is not empty. Pass --overwrite: {case_dir}")
    layout_dir = case_dir / "layout"
    routing_dir = case_dir / "routing"
    sim_dir = case_dir / "simulation"
    reports_dir = case_dir / "reports"
    for directory in (layout_dir, routing_dir, sim_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    pitch_mm = args.bump_pitch_mm if args.bump_pitch_mm is not None else (args.bump_pitch_um or 130.0) / 1000.0
    trace_width_mm, clearance_mm = choose_width_and_clearance(pitch_mm, args.trace_width_mm, args.clearance_mm)
    grid_mm = args.grid_mm or min(0.025, max(0.005, pitch_mm / 4.0))
    margin_x_mm = max(1.0, pitch_mm * 8.0)
    margin_y_mm = max(1.0, pitch_mm * 4.0)

    if args.endpoint_map:
        endpoints, endpoint_payload = load_endpoint_map(args.endpoint_map)
        endpoint_validation = validate_endpoint_map_for_routing(
            endpoint_payload,
            allow_proxy_fanout=args.allow_proxy_fanout_endpoints,
        )
        endpoint_source_type = endpoint_payload.get("source_type", "provided")
    else:
        endpoints, endpoint_payload = synthetic_endpoint_map(
            lane_count=args.lane_count,
            pitch_mm=pitch_mm,
            channel_length_mm=args.channel_length_mm,
            columns=args.columns,
            margin_x_mm=margin_x_mm,
            margin_y_mm=margin_y_mm,
        )
        endpoint_validation = validate_endpoint_map_for_routing(
            endpoint_payload,
            allow_proxy_fanout=True,
        )
        endpoint_source_type = "synthetic"

    if len(endpoints) != args.lane_count:
        args.lane_count = len(endpoints)

    x_values = [point for endpoint in endpoints for point in (endpoint.tx[0], endpoint.rx[0])]
    y_values = [point for endpoint in endpoints for point in (endpoint.tx[1], endpoint.rx[1])]
    board_width = max(x_values) + margin_x_mm
    board_height = max(max(y_values) + margin_y_mm, 2.5)
    bounds = (0.15, 0.15, board_width - 0.15, board_height - 0.15)
    keepout = trace_width_mm + clearance_mm

    sorted_endpoints = sorted(endpoints, key=lambda item: (item.tx[1], item.tx[0], item.name))
    accepted_paths: list[list[tuple[float, float]]] = []
    routes = []
    route_failures = []
    for endpoint in sorted_endpoints:
        try:
            points = astar_route(endpoint.tx, endpoint.rx, grid_mm, bounds, accepted_paths, keepout)
            accepted_paths.append(points)
            routes.append(
                {
                    "net": endpoint.name,
                    "layer": endpoint.layer,
                    "points": points,
                    "length_mm": rounded(path_length(points)),
                    "algorithm": "deterministic_astar_octile",
                    "allow_diagonal": True,
                }
            )
        except Exception as exc:
            route_failures.append({"net": endpoint.name, "error": str(exc)})

    endpoint_map_path = routing_dir / "endpoint_map.json"
    write_json(endpoint_map_path, endpoint_payload)
    route_request = {
        "algorithm": "deterministic_astar_octile",
        "allow_diagonal": True,
        "grid_mm": grid_mm,
        "trace_width_mm": trace_width_mm,
        "clearance_mm": clearance_mm,
        "target_impedance_ohm": args.target_impedance_ohm,
        "impedance_estimate": {
            "model": "pre_layout_microstrip_or_stripline_proxy",
            "dk": args.dk,
            "df": args.df,
            "reference_layer": "In1.Cu" if args.layer_count >= 4 else "B.Cu",
            "status": "rough_pre_layout_estimate",
        },
        "bounds_mm": {"x1": bounds[0], "y1": bounds[1], "x2": bounds[2], "y2": bounds[3]},
        "endpoint_map": str(endpoint_map_path),
    }
    route_result = {
        "result": "PASS" if not route_failures else "FAIL",
        "route_count": len(routes),
        "failures": route_failures,
        "settings": route_request,
        "endpoint_map_validation": endpoint_validation,
        "routes": routes,
        "lengths_mm": {route["net"]: route["length_mm"] for route in routes},
        "max_length_delta_mm": rounded(max((route["length_mm"] for route in routes), default=0) - min((route["length_mm"] for route in routes), default=0)),
    }
    write_json(routing_dir / "route_request.json", route_request)
    write_json(routing_dir / "route_result.json", route_result)

    board_path = layout_dir / f"{case_name}.kicad_pcb"
    project_path = layout_dir / f"{case_name}.kicad_pro"
    schematic_path = layout_dir / f"{case_name}.kicad_sch"
    project_path.write_text(kicad_project(case_name) + "\n", encoding="utf-8")
    schematic_path.write_text(
        f"(kicad_sch (version 20250114) (generator \"sipi-harness-generic-channel\") (uuid \"{kid()}\"))\n",
        encoding="utf-8",
    )
    launch_width_mm = min(max(trace_width_mm * 1.25, 0.020), pitch_mm * 0.55)
    write_kicad_board(
        path=board_path,
        case_name=case_name,
        endpoints=endpoints,
        routes=routes,
        width_mm=board_width,
        height_mm=board_height,
        trace_width_mm=trace_width_mm,
        launch_width_mm=launch_width_mm,
        layer_count=args.layer_count,
        dk=args.dk,
        df=args.df,
    )

    port_intents = {
        "unit": "mm",
        "port_method": "edb_polygon_edge",
        "expected_port_count": len(routes) * 2,
        "source": "generic_channel_case_generator",
        "ports": [],
    }
    order = 1
    for route in routes:
        points = route["points"]
        for role, point in (("tx", points[0]), ("rx", points[-1])):
            port_intents["ports"].append(
                {
                    "name": f"P_{route['net']}_{role.upper()}",
                    "type": "circuit",
                    "port_method": "edb_polygon_edge",
                    "signal_net": route["net"],
                    "reference_net": "GND",
                    "positive_layer": route["layer"],
                    "negative_layer": "In1.Cu" if args.layer_count >= 4 else "B.Cu",
                    "positive_x": point[0],
                    "positive_y": point[1],
                    "expected_impedance_ohm": args.target_impedance_ohm,
                    "expected_order": order,
                    "role": role,
                    "placement_rule": "polygon_edge_signal_to_local_reference_edge",
                    "max_port_edge_length_mm": 0.30,
                    "max_port_edge_distance_mm": 0.05,
                }
            )
            order += 1
    port_intents_path = sim_dir / "hfss3dlayout_port_intents.json"
    write_json(port_intents_path, port_intents)

    manifest = {
        "case_name": case_name,
        "bundle_id": case_name,
        "status": "PCB_PACKAGE_READY" if route_result["result"] == "PASS" else "PCB_PACKAGE_BLOCKED",
        "interface": args.interface,
        "package_class": args.package_class,
        "data_rate_gbps": args.data_rate_gbps,
        "channel_length_mm": args.channel_length_mm,
        "lane_count": len(endpoints),
        "source_status": args.source_status,
        "endpoint_source_type": endpoint_source_type,
        "compliance_status": "blocked_until_reviewed_spec_evidence" if endpoint_source_type == "synthetic" else "engineering_candidate",
        "board": {
            "package_type": args.package_class,
            "widthMm": board_width,
            "heightMm": board_height,
            "channelLengthMm": args.channel_length_mm,
            "lanes": len(endpoints),
            "layer_count": args.layer_count,
            "stackup": "4L signal/reference/reference/signal" if args.layer_count >= 4 else "2L signal/reference",
        },
        "geometry_review": {
            "routing_algorithm": "deterministic_astar_octile",
            "allow_diagonal": True,
            "route_result": route_result["result"],
            "trace_width_mm": trace_width_mm,
            "clearance_mm": clearance_mm,
            "launch_width_mm_for_aedb_converter": launch_width_mm,
            "reference_plane": "continuous GND zones on reference layer(s)",
            "endpoint_map_validation": endpoint_validation,
        },
        "artifacts": {
            "kicad_project": str(project_path),
            "kicad_board": str(board_path),
            "kicad_schematic": str(schematic_path),
            "endpoint_map": str(endpoint_map_path),
            "route_request": str(routing_dir / "route_request.json"),
            "route_result": str(routing_dir / "route_result.json"),
            "hfss3dlayout_port_intents": str(port_intents_path),
            "design_strategy_yaml": str(args.strategy.resolve()) if args.strategy else None,
            "spec_evidence": str(args.spec_evidence.resolve()) if args.spec_evidence else None,
        },
        "next_actions": [
            "Run check:kicad-geometry before HFSS handoff.",
            "Run check:port-launch before HFSS import.",
            "Render kicad_layout_preview.png for stage review.",
            "Use edb_polygon_edge Gap ports for HFSS 3D Layout import.",
        ],
    }
    manifest_path = case_dir / "manifest.json"
    write_json(manifest_path, manifest)
    summary = {
        "ok": route_result["result"] == "PASS",
        "case_dir": str(case_dir),
        "manifest": str(manifest_path),
        "board": str(board_path),
        "port_intents": str(port_intents_path),
        "route_result": str(routing_dir / "route_result.json"),
        "endpoint_map": str(endpoint_map_path),
        "route_failures": route_failures,
    }
    print(json.dumps(summary, indent=2))
    return 0 if route_result["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
