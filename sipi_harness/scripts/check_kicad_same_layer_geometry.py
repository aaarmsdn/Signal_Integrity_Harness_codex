from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


COPPER_LAYERS = {"F.Cu", "B.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"}


def fnum(value: str) -> float:
    return float(value.replace(",", "."))


def dist_point_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx = bx - ax
    vy = by - ay
    wx = px - ax
    wy = py - ay
    length2 = vx * vx + vy * vy
    if length2 <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length2))
    cx = ax + t * vx
    cy = ay + t * vy
    return math.hypot(px - cx, py - cy)


def orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)


def on_segment(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> bool:
    eps = 1e-9
    return (
        min(ax, cx) - eps <= bx <= max(ax, cx) + eps
        and min(ay, cy) - eps <= by <= max(ay, cy) + eps
    )


def centerlines_intersect(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax1, ay1, ax2, ay2 = a["x1"], a["y1"], a["x2"], a["y2"]
    bx1, by1, bx2, by2 = b["x1"], b["y1"], b["x2"], b["y2"]
    o1 = orientation(ax1, ay1, ax2, ay2, bx1, by1)
    o2 = orientation(ax1, ay1, ax2, ay2, bx2, by2)
    o3 = orientation(bx1, by1, bx2, by2, ax1, ay1)
    o4 = orientation(bx1, by1, bx2, by2, ax2, ay2)
    eps = 1e-9
    if o1 * o2 < -eps and o3 * o4 < -eps:
        return True
    if abs(o1) <= eps and on_segment(ax1, ay1, bx1, by1, ax2, ay2):
        return True
    if abs(o2) <= eps and on_segment(ax1, ay1, bx2, by2, ax2, ay2):
        return True
    if abs(o3) <= eps and on_segment(bx1, by1, ax1, ay1, bx2, by2):
        return True
    if abs(o4) <= eps and on_segment(bx1, by1, ax2, ay2, bx2, by2):
        return True
    return False


def dist_segment_segment(a: dict[str, Any], b: dict[str, Any]) -> float:
    if centerlines_intersect(a, b):
        return 0.0
    return min(
        dist_point_segment(a["x1"], a["y1"], b["x1"], b["y1"], b["x2"], b["y2"]),
        dist_point_segment(a["x2"], a["y2"], b["x1"], b["y1"], b["x2"], b["y2"]),
        dist_point_segment(b["x1"], b["y1"], a["x1"], a["y1"], a["x2"], a["y2"]),
        dist_point_segment(b["x2"], b["y2"], a["x1"], a["y1"], a["x2"], a["y2"]),
    )


def parse_board(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")

    nets: dict[int, str] = {}
    for match in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', text):
        nets[int(match.group(1))] = match.group(2)

    segments: list[dict[str, Any]] = []
    for idx, match in enumerate(
        re.finditer(
            r'\(segment\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+\(width\s+([-\d.]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)',
            text,
        )
    ):
        x1, y1, x2, y2, width = [fnum(item) for item in match.groups()[:5]]
        layer = match.group(6)
        net = int(match.group(7))
        segments.append(
            {
                "id": f"segment_{idx}",
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": width,
                "layer": layer,
                "net": net,
                "net_name": nets.get(net, str(net)),
            }
        )

    vias: list[dict[str, Any]] = []
    for idx, match in enumerate(
        re.finditer(
            r'\(via\s+\(at\s+([-\d.]+)\s+([-\d.]+)\)\s+\(size\s+([-\d.]+)\).*?\(net\s+(\d+)\)',
            text,
            re.DOTALL,
        )
    ):
        x, y, size = [fnum(item) for item in match.groups()[:3]]
        net = int(match.group(4))
        vias.append(
            {
                "id": f"via_{idx}",
                "x": x,
                "y": y,
                "radius": size / 2,
                "layers": sorted(COPPER_LAYERS),
                "net": net,
                "net_name": nets.get(net, str(net)),
            }
        )

    pads: list[dict[str, Any]] = []
    for fp_idx, footprint in enumerate(re.finditer(r'\(footprint\s+"[^"]+".*?\n\t\)', text, re.DOTALL)):
        block = footprint.group(0)
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)', block)
        if not at:
            continue
        fx, fy = fnum(at.group(1)), fnum(at.group(2))
        ref = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        ref_name = ref.group(1) if ref else f"footprint_{fp_idx}"
        for pad_idx, pad in enumerate(
            re.finditer(
                r'\(pad\s+"([^"]*)"\s+(\S+)\s+(\S+)\s+\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)\s+\(size\s+([-\d.]+)\s+([-\d.]+)\)(.*?)\n\t\t\)',
                block,
                re.DOTALL,
            )
        ):
            pad_name = pad.group(1)
            pad_type = pad.group(2)
            shape = pad.group(3)
            px = fx + fnum(pad.group(4))
            py = fy + fnum(pad.group(5))
            sx = fnum(pad.group(6))
            sy = fnum(pad.group(7))
            rest = pad.group(8)
            net_match = re.search(r'\(net\s+(\d+)(?:\s+"([^"]+)")?', rest)
            if not net_match:
                continue
            net = int(net_match.group(1))
            layer_match = re.search(r'\(layers\s+([^)]+)\)', rest)
            layer_tokens = re.findall(r'"([^"]+)"', layer_match.group(1)) if layer_match else []
            if pad_type == "thru_hole" or "*.Cu" in layer_tokens:
                layers = sorted(COPPER_LAYERS)
            else:
                layers = sorted(layer for layer in layer_tokens if layer in COPPER_LAYERS)
            if not layers:
                continue
            pads.append(
                {
                    "id": f"{ref_name}.{pad_name or pad_idx}",
                    "x": px,
                    "y": py,
                    "radius": max(sx, sy) / 2,
                    "sx": sx,
                    "sy": sy,
                    "shape": shape,
                    "layers": layers,
                    "net": net,
                    "net_name": net_match.group(2) or nets.get(net, str(net)),
                }
            )

    return {"nets": nets, "segments": segments, "pads": pads, "vias": vias}


def add_violation(violations: list[dict[str, Any]], kind: str, layer: str, a: dict[str, Any], b: dict[str, Any], distance: float, limit: float) -> None:
    violations.append(
        {
            "kind": kind,
            "layer": layer,
            "a": {"id": a["id"], "net": a["net_name"]},
            "b": {"id": b["id"], "net": b["net_name"]},
            "distance_mm": round(distance, 6),
            "limit_mm": round(limit, 6),
        }
    )


def check(board: dict[str, Any], clearance_mm: float) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    segments = [seg for seg in board["segments"] if seg["layer"] in COPPER_LAYERS]
    pads = board["pads"]
    vias = board["vias"]

    for idx, a in enumerate(segments):
        for b in segments[idx + 1 :]:
            if a["layer"] != b["layer"] or a["net"] == b["net"]:
                continue
            distance = dist_segment_segment(a, b)
            limit = (a["width"] + b["width"]) / 2 + clearance_mm
            if distance <= limit + 1e-9:
                kind = "same_layer_crossing_or_short" if distance <= 1e-9 else "same_layer_trace_clearance"
                add_violation(violations, kind, a["layer"], a, b, distance, limit)

    circular_items = pads + vias
    for seg in segments:
        for item in circular_items:
            if seg["net"] == item["net"] or seg["layer"] not in item["layers"]:
                continue
            distance = dist_point_segment(item["x"], item["y"], seg["x1"], seg["y1"], seg["x2"], seg["y2"])
            limit = seg["width"] / 2 + item["radius"] + clearance_mm
            if distance <= limit + 1e-9:
                add_violation(violations, "same_layer_trace_to_pad_or_via_short", seg["layer"], seg, item, distance, limit)

    for idx, a in enumerate(circular_items):
        for b in circular_items[idx + 1 :]:
            if a["net"] == b["net"]:
                continue
            for layer in sorted(set(a["layers"]) & set(b["layers"])):
                distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                limit = a["radius"] + b["radius"] + clearance_mm
                if distance <= limit + 1e-9:
                    add_violation(violations, "same_layer_pad_or_via_overlap", layer, a, b, distance, limit)

    return {
        "result": "PASS" if not violations else "FAIL",
        "clearance_mm": clearance_mm,
        "segment_count": len(segments),
        "pad_count": len(pads),
        "via_count": len(vias),
        "violation_count": len(violations),
        "violations": violations,
    }


def update_manifest(path: Path, summary: dict[str, Any], output: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    checks = manifest.setdefault("geometry_checks", {})
    checks["same_layer_crossing_short"] = {
        "result": summary["result"],
        "path": str(output),
        "violation_count": summary["violation_count"],
        "clearance_mm": summary["clearance_mm"],
    }
    review = manifest.setdefault("geometry_review", {})
    review["same_layer_crossing_short"] = summary["result"]
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check KiCad board for same-layer crossing/short geometry violations.")
    parser.add_argument("--board", required=True, type=Path, help="Input .kicad_pcb file.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON summary.")
    parser.add_argument("--manifest", type=Path, help="Optional case manifest to update.")
    parser.add_argument("--clearance-mm", default=0.0, type=float, help="Extra copper-to-copper clearance beyond physical overlap.")
    parser.add_argument("--allow-fail", action="store_true", help="Write the report but return success even on FAIL.")
    args = parser.parse_args()

    board = parse_board(args.board)
    summary = check(board, args.clearance_mm)
    summary["board"] = str(args.board)
    summary["note"] = "Authoritative pre-HFSS gate for same-layer crossings/shorts. KiCad preview images are not sufficient evidence."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.manifest:
        update_manifest(args.manifest, summary, args.output)
    print(json.dumps({"result": summary["result"], "violations": summary["violation_count"], "output": str(args.output)}, indent=2))
    return 0 if summary["result"] == "PASS" or args.allow_fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
