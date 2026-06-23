from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check HFSS 3D Layout port launch geometry for polygon-edge or coordinate circuit ports."
    )
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--port-intents", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--min-via-distance-mm", type=float, default=0.050)
    parser.add_argument("--min-pad-distance-mm", type=float, default=0.020)
    parser.add_argument("--reference-via-clearance-mm", type=float, default=0.030)
    parser.add_argument(
        "--max-circuit-port-span-mm",
        type=float,
        default=0.15,
        help=(
            "Maximum distance between the positive signal terminal and negative "
            "reference terminal for coordinate circuit-port override flows. Long "
            "terminal spans can create visible ports that solve but do not export "
            "valid network data."
        ),
    )
    parser.add_argument(
        "--allow-path-edge",
        action="store_true",
        help=(
            "Allow edb_path_edge as an explicit debug override. Normal harness "
            "handoff must use edb_polygon_edge because path-edge ports can attach "
            "to a long trace side or to the wrong edge after import."
        ),
    )
    return parser.parse_args()


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance: float,
) -> bool:
    length = distance(start, end)
    if length <= 1e-12:
        return distance(point, start) <= tolerance
    cross = abs((point[0] - start[0]) * (end[1] - start[1]) - (point[1] - start[1]) * (end[0] - start[0]))
    if cross / length > tolerance:
        return False
    dot = (point[0] - start[0]) * (end[0] - start[0]) + (point[1] - start[1]) * (end[1] - start[1])
    return -tolerance <= dot <= length * length + tolerance


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    x, y = point
    j = len(polygon) - 1
    for i, pi in enumerate(polygon):
        pj = polygon[j]
        if point_on_segment(point, pi, pj, 1e-9):
            return True
        if (pi[1] > y) != (pj[1] > y):
            x_cross = (pj[0] - pi[0]) * (y - pi[1]) / (pj[1] - pi[1]) + pi[0]
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def parse_board(board_text: str) -> dict[str, Any]:
    net_names = {int(match.group(1)): match.group(2) for match in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', board_text)}
    vias = []
    for match in re.finditer(r"\(via\s+\(at\s+([-\d.]+)\s+([-\d.]+)\)(.*?)\n\t?\)", board_text, re.S):
        body = match.group(3)
        net = re.search(r"\(net\s+(\d+)\)", body)
        size = re.search(r"\(size\s+([-\d.]+)\)", body)
        drill = re.search(r"\(drill\s+([-\d.]+)\)", body)
        vias.append(
            {
                "x": float(match.group(1)),
                "y": float(match.group(2)),
                "net_id": int(net.group(1)) if net else None,
                "size_mm": float(size.group(1)) if size else None,
                "drill_mm": float(drill.group(1)) if drill else None,
            }
        )

    pads = []
    for footprint in re.finditer(r"\(footprint\b.*?\n\t\)", board_text, re.S):
        text = footprint.group(0)
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)", text)
        pad = re.search(r'\(pad\s+"[^"]+"\s+smd\s+\w+.*?\(size\s+([-\d.]+)\s+([-\d.]+)\).*?\(layers\s+([^)]+)\).*?\(net\s+(\d+)\s+"([^"]*)"\)', text, re.S)
        if at and pad:
            pads.append(
                {
                    "x": float(at.group(1)),
                    "y": float(at.group(2)),
                    "size_x_mm": float(pad.group(1)),
                    "size_y_mm": float(pad.group(2)),
                    "layers": re.findall(r'"([^"]+)"', pad.group(3)),
                    "net_id": int(pad.group(4)),
                    "net_name": pad.group(5),
                }
            )

    segments = []
    for match in re.finditer(
        r'\(segment\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+\(width\s+([-\d.]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)',
        board_text,
        re.S,
    ):
        net_id = int(match.group(7))
        segments.append(
            {
                "start": (float(match.group(1)), float(match.group(2))),
                "end": (float(match.group(3)), float(match.group(4))),
                "width_mm": float(match.group(5)),
                "layer": match.group(6),
                "net_id": net_id,
                "net_name": net_names.get(net_id, ""),
            }
        )

    zones = []
    for match in re.finditer(r'\(zone\b(.*?)(?=\n\t\(zone\b|\n\))', board_text, re.S):
        text = match.group(1)
        net_name = re.search(r'\(net_name\s+"([^"]*)"\)', text)
        net = re.search(r"\(net\s+(\d+)\)", text)
        layer = re.search(r'\(layer\s+"([^"]+)"\)', text)
        pts = [(float(x), float(y)) for x, y in re.findall(r"\(xy\s+([-\d.]+)\s+([-\d.]+)\)", text)]
        if layer and pts:
            net_id = int(net.group(1)) if net else None
            zones.append(
                {
                    "layer": layer.group(1),
                    "net_id": net_id,
                    "net_name": net_name.group(1) if net_name else net_names.get(net_id, ""),
                    "points": pts,
                }
            )
    return {"net_names": net_names, "vias": vias, "pads": pads, "segments": segments, "zones": zones}


def point_on_pad(point: tuple[float, float], pad: dict[str, Any], layer: str | None = None, margin: float = 0.002) -> bool:
    if layer and layer not in pad.get("layers", []):
        return False
    return (
        abs(point[0] - pad["x"]) <= pad.get("size_x_mm", 0.0) / 2.0 + margin
        and abs(point[1] - pad["y"]) <= pad.get("size_y_mm", 0.0) / 2.0 + margin
    )


def point_on_net_copper(
    point: tuple[float, float],
    layer: str,
    net_name: str,
    board: dict[str, Any],
    tolerance: float = 0.002,
) -> tuple[bool, list[str]]:
    hits = []
    for pad in board["pads"]:
        if pad.get("net_name") == net_name and point_on_pad(point, pad, layer, tolerance):
            hits.append("pad")
    for segment in board["segments"]:
        if segment.get("net_name") == net_name and segment.get("layer") == layer:
            if point_on_segment(point, segment["start"], segment["end"], segment.get("width_mm", 0.0) / 2.0 + tolerance):
                hits.append("segment")
    for zone in board["zones"]:
        if zone.get("net_name") == net_name and zone.get("layer") == layer and point_in_polygon(point, zone["points"]):
            hits.append("zone")
    return bool(hits), sorted(set(hits))


def net_layer_has_copper(layer: str, net_name: str, board: dict[str, Any]) -> tuple[bool, list[str]]:
    hits = []
    for pad in board["pads"]:
        if pad.get("net_name") == net_name and layer in pad.get("layers", []):
            hits.append("pad")
    for segment in board["segments"]:
        if segment.get("net_name") == net_name and segment.get("layer") == layer:
            hits.append("segment")
    for zone in board["zones"]:
        if zone.get("net_name") == net_name and zone.get("layer") == layer:
            hits.append("zone")
    return bool(hits), sorted(set(hits))


def main() -> int:
    args = parse_args()
    board_text = args.board.read_text(encoding="utf-8", errors="ignore")
    port_spec = json.loads(args.port_intents.read_text(encoding="utf-8-sig"))
    board = parse_board(board_text)
    vias = board["vias"]
    pads = board["pads"]
    violations = []
    checks = []
    for port in port_spec.get("ports", []):
        signal_net = str(port.get("signal_net") or port.get("net") or "")
        reference_net = str(port.get("reference_net") or "GND")
        positive_layer = str(port.get("positive_layer") or port.get("pos_layer") or "")
        negative_layer = str(port.get("negative_layer") or port.get("neg_layer") or "")
        positive_x_raw = port.get("positive_x")
        positive_y_raw = port.get("positive_y")
        negative_x_raw = port.get("negative_x")
        negative_y_raw = port.get("negative_y")
        port_method = str(port.get("port_method") or port.get("type") or port_spec.get("port_method") or "edb_polygon_edge")
        edge_method = port_method in {
            "edb_polygon_edge",
            "edb_path_edge",
            "polygon_edge_signal_to_local_reference_edge",
        }
        has_positive = positive_x_raw is not None and positive_y_raw is not None
        has_negative = negative_x_raw is not None and negative_y_raw is not None
        if port_method == "edb_path_edge" and not args.allow_path_edge:
            item = {
                "port": port.get("name"),
                "signal_net": signal_net,
                "reference_net": reference_net,
                "port_method": port_method,
                "positive_x": positive_x_raw,
                "positive_y": positive_y_raw,
                "positive_layer": positive_layer,
                "negative_layer": negative_layer,
                "placement_rule": port.get("placement_rule"),
            }
            checks.append(item)
            violations.append(
                {
                    **item,
                    "rule": "path_edge_port_method_requires_explicit_override",
                    "message": (
                        "edb_path_edge is not allowed in normal harness runs. It can "
                        "select a long trace side or the wrong Start/End edge. Use "
                        "edb_polygon_edge with endpoint launch pads/tabs, or rerun "
                        "check:port-launch with --allow-path-edge only for a documented "
                        "debug experiment that will not be treated as a valid handoff."
                    ),
                }
            )
            continue
        if edge_method:
            if has_negative:
                item = {
                    "port": port.get("name"),
                    "signal_net": signal_net,
                    "reference_net": reference_net,
                    "port_method": port_method,
                    "positive_x": positive_x_raw,
                    "positive_y": positive_y_raw,
                    "negative_x": negative_x_raw,
                    "negative_y": negative_y_raw,
                    "positive_layer": positive_layer,
                    "negative_layer": negative_layer,
                    "placement_rule": port.get("placement_rule"),
                }
                checks.append(item)
                violations.append(
                    {
                        **item,
                        "rule": "edge_port_intent_contains_coordinate_override",
                        "message": (
                            "Do not put negative_x/negative_y in edb_polygon_edge or edb_path_edge "
                            "port intents. Select a local reference primitive/edge through "
                            "reference_net, negative_layer, and reference_selector metadata. "
                            "Use coordinate fields only with an explicit coordinate-port debug override."
                        ),
                    }
                )
                continue
            if not has_positive:
                item = {
                    "port": port.get("name"),
                    "signal_net": signal_net,
                    "reference_net": reference_net,
                    "port_method": port_method,
                    "positive_x": positive_x_raw,
                    "positive_y": positive_y_raw,
                    "positive_layer": positive_layer,
                    "negative_layer": negative_layer,
                    "positive_on_signal_copper": False,
                    "positive_copper_hits": [],
                    "reference_geometry_available": False,
                    "reference_geometry_hits": [],
                    "placement_rule": port.get("placement_rule"),
                }
                checks.append(item)
                violations.append(
                    {
                        **item,
                        "rule": "missing_signal_launch_coordinate",
                        "message": "Polygon-edge HFSS ports require positive_x/positive_y to select the signal launch edge.",
                    }
                )
                continue
            x = float(positive_x_raw)
            y = float(positive_y_raw)
            positive_on_signal, positive_hits = point_on_net_copper((x, y), positive_layer, signal_net, board)
            reference_available, reference_hits = net_layer_has_copper(negative_layer, reference_net, board)
            nearest_via = min((distance((x, y), (via["x"], via["y"])), via) for via in vias) if vias else None
            item = {
                "port": port.get("name"),
                "signal_net": signal_net,
                "reference_net": reference_net,
                "port_method": port_method,
                "positive_x": x,
                "positive_y": y,
                "positive_layer": positive_layer,
                "negative_layer": negative_layer,
                "positive_on_signal_copper": positive_on_signal,
                "positive_copper_hits": positive_hits,
                "reference_geometry_available": reference_available,
                "reference_geometry_hits": reference_hits,
                "nearest_via_distance_mm": nearest_via[0] if nearest_via else None,
                "placement_rule": port.get("placement_rule"),
            }
            checks.append(item)
            if not positive_on_signal:
                violations.append(
                    {
                        **item,
                        "rule": "signal_launch_not_on_signal_copper",
                        "message": "Move positive_x/positive_y onto the named signal net so the polygon edge selector can find a launch edge.",
                    }
                )
            if not reference_available:
                violations.append(
                    {
                        **item,
                        "rule": "reference_geometry_missing",
                        "message": "Polygon-edge HFSS ports require local reference-net copper on negative_layer for the reference edge.",
                    }
                )
            continue
        if not has_positive or not has_negative:
            item = {
                "port": port.get("name"),
                "signal_net": signal_net,
                "port_method": port_method,
                "positive_x": positive_x_raw,
                "positive_y": positive_y_raw,
                "negative_x": negative_x_raw,
                "negative_y": negative_y_raw,
                "has_two_point_reference": False,
                "positive_layer": positive_layer,
                "negative_layer": negative_layer,
                "positive_on_signal_copper": False,
                "positive_copper_hits": [],
                "negative_on_reference_copper": False,
                "negative_copper_hits": [],
                "nearest_via_distance_mm": None,
                "nearest_reference_via_distance_mm": None,
                "reference_via_clearance_required_mm": None,
                "nearest_same_net_pad_distance_mm": None,
                "placement_rule": port.get("placement_rule"),
            }
            checks.append(item)
            violations.append(
                {
                    **item,
                    "rule": "missing_two_point_circuit_port",
                    "message": "Coordinate HFSS circuit-port override requires explicit positive_x/positive_y and negative_x/negative_y; use edb_polygon_edge unless coordinate ports are explicitly required.",
                }
            )
            continue
        x = float(positive_x_raw)
        y = float(positive_y_raw)
        negative_x = float(negative_x_raw)
        negative_y = float(negative_y_raw)
        has_two_point_reference = distance((x, y), (negative_x, negative_y)) > 1e-9
        terminal_span_mm = distance((x, y), (negative_x, negative_y))
        positive_on_signal, positive_hits = point_on_net_copper((x, y), positive_layer, signal_net, board)
        negative_on_reference, negative_hits = point_on_net_copper((negative_x, negative_y), negative_layer, reference_net, board)
        nearest_via = min((distance((x, y), (via["x"], via["y"])), via) for via in vias) if vias else None
        nearest_ref_via = min((distance((negative_x, negative_y), (via["x"], via["y"])), via) for via in vias) if vias else None
        same_net_pads = [pad for pad in pads if pad["net_name"] == signal_net]
        nearest_pad = min((distance((x, y), (pad["x"], pad["y"])), pad) for pad in same_net_pads) if same_net_pads else None
        ref_clearance_required = None
        if nearest_ref_via:
            via = nearest_ref_via[1]
            via_radius = ((via.get("size_mm") or via.get("drill_mm") or 0.0) / 2.0)
            ref_clearance_required = max(args.min_via_distance_mm, via_radius + args.reference_via_clearance_mm)
        item = {
            "port": port.get("name"),
            "signal_net": signal_net,
            "port_method": port_method,
            "positive_x": x,
            "positive_y": y,
            "negative_x": negative_x,
            "negative_y": negative_y,
            "terminal_span_mm": terminal_span_mm,
            "has_two_point_reference": has_two_point_reference,
            "positive_layer": positive_layer,
            "negative_layer": negative_layer,
            "positive_on_signal_copper": positive_on_signal,
            "positive_copper_hits": positive_hits,
            "negative_on_reference_copper": negative_on_reference,
            "negative_copper_hits": negative_hits,
            "nearest_via_distance_mm": nearest_via[0] if nearest_via else None,
            "nearest_reference_via_distance_mm": nearest_ref_via[0] if nearest_ref_via else None,
            "reference_via_clearance_required_mm": ref_clearance_required,
            "nearest_same_net_pad_distance_mm": nearest_pad[0] if nearest_pad else None,
            "placement_rule": port.get("placement_rule"),
        }
        checks.append(item)
        if not has_two_point_reference:
            violations.append(
                {
                    **item,
                    "rule": "missing_two_point_circuit_port",
                    "message": "HFSS handoff requires explicit two-point circuit-port terminals: positive_x/positive_y and negative_x/negative_y.",
                }
            )
        elif terminal_span_mm > args.max_circuit_port_span_mm:
            violations.append(
                {
                    **item,
                    "rule": "circuit_port_terminal_span_too_long",
                    "maximum_mm": args.max_circuit_port_span_mm,
                    "message": (
                        "Place the negative reference terminal on nearby solid reference copper "
                        "or a local GND port tab facing the signal launch edge. A distant plane "
                        "coordinate can create a visible but non-exportable HFSS 3D Layout port."
                    ),
                }
            )
        if not positive_on_signal:
            violations.append(
                {
                    **item,
                    "rule": "positive_terminal_not_on_signal_copper",
                    "message": "Move positive_x/positive_y onto the named signal net's pad or routed copper on positive_layer.",
                }
            )
        if not negative_on_reference:
            violations.append(
                {
                    **item,
                    "rule": "negative_terminal_not_on_reference_copper",
                    "message": "Move negative_x/negative_y onto solid reference-net copper on negative_layer; do not pass an empty plane coordinate to HFSS.",
                }
            )
        if has_two_point_reference:
            if nearest_ref_via and nearest_ref_via[0] < ref_clearance_required:
                violations.append(
                    {
                        **item,
                        "rule": "reference_terminal_too_close_to_via_hole",
                        "minimum_mm": ref_clearance_required,
                        "message": "Move negative_x/negative_y onto solid reference-plane copper outside the via hole/antipad clearance.",
                    }
                )
            continue
        if nearest_via and nearest_via[0] < args.min_via_distance_mm:
            violations.append(
                {
                    **item,
                    "rule": "port_too_close_to_via",
                    "minimum_mm": args.min_via_distance_mm,
                    "message": (
                        "For the default edge-port flow, select a short local signal launch edge and "
                        "nearby solid reference edge outside the via hole/antipad keepout. Use "
                        "negative_x/negative_y only for an explicitly approved coordinate-port debug override."
                    ),
                }
            )
        if nearest_pad and nearest_pad[0] < args.min_pad_distance_mm:
            violations.append(
                {
                    **item,
                    "rule": "port_too_close_to_pad_center",
                    "minimum_mm": args.min_pad_distance_mm,
                    "message": (
                        "Move the selected launch to a terminal-like edge/tab instead of the pad center. "
                        "Do not add negative_x/negative_y unless this case is intentionally using "
                        "coordinate-port debug override."
                    ),
                }
            )

    summary = {
        "result": "PASS" if not violations else "FAIL",
        "board": str(args.board),
        "port_intents": str(args.port_intents),
        "port_count": len(port_spec.get("ports", [])),
        "via_count": len(vias),
        "pad_count": len(pads),
        "segment_count": len(board["segments"]),
        "zone_count": len(board["zones"]),
        "min_via_distance_mm": args.min_via_distance_mm,
        "min_pad_distance_mm": args.min_pad_distance_mm,
        "reference_via_clearance_mm": args.reference_via_clearance_mm,
        "max_circuit_port_span_mm": args.max_circuit_port_span_mm,
        "checks": checks,
        "violations": violations,
        "note": "HFSS 3D Layout handoff defaults to AEDB polygon-edge ports: positive launch coordinate selects signal edge; reference net/layer must contain local copper. Coordinate two-point ports are override/debug only.",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
