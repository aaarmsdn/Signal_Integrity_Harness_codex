from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle


LAYER_COLORS = {
    "F.Cu": "#0b7d35",
    "B.Cu": "#1f5fbf",
    "In1.Cu": "#b46b00",
    "In2.Cu": "#7a3db8",
    "Edge.Cuts": "#111827",
}


def parse_float(value: str) -> float:
    return float(value.replace(",", "."))


def parse_board(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")

    edges = []
    for match in re.finditer(
        r'\(gr_line\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\).*?\(layer\s+"Edge\.Cuts"\)',
        text,
        re.DOTALL,
    ):
        edges.append(tuple(parse_float(item) for item in match.groups()))

    segments = []
    for match in re.finditer(
        r'\(segment\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+\(width\s+([-\d.]+)\)\s+\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)',
        text,
    ):
        x1, y1, x2, y2, width = [parse_float(item) for item in match.groups()[:5]]
        layer = match.group(6)
        net = int(match.group(7))
        segments.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": width, "layer": layer, "net": net})

    vias = []
    for match in re.finditer(
        r'\(via\s+\(at\s+([-\d.]+)\s+([-\d.]+)\)\s+\(size\s+([-\d.]+)\).*?\(net\s+(\d+)\)',
        text,
        re.DOTALL,
    ):
        x, y, size = [parse_float(item) for item in match.groups()[:3]]
        vias.append({"x": x, "y": y, "size": size, "net": int(match.group(4))})

    pads = []
    for footprint in re.finditer(r'\(footprint\s+"[^"]+".*?\n\t\)', text, re.DOTALL):
        block = footprint.group(0)
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)', block)
        if not at:
            continue
        fx, fy = parse_float(at.group(1)), parse_float(at.group(2))
        ref = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        pad = re.search(
            r'\(pad\s+"[^"]+"\s+\S+\s+(\S+)\s+\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)\s+\(size\s+([-\d.]+)\s+([-\d.]+)\).*?\(net\s+(\d+)(?:\s+"([^"]+)")?',
            block,
            re.DOTALL,
        )
        if not pad:
            continue
        shape = pad.group(1)
        px = fx + parse_float(pad.group(2))
        py = fy + parse_float(pad.group(3))
        sx = parse_float(pad.group(4))
        sy = parse_float(pad.group(5))
        pads.append(
            {
                "x": px,
                "y": py,
                "sx": sx,
                "sy": sy,
                "shape": shape,
                "net": int(pad.group(6)),
                "net_name": pad.group(7) or "",
                "ref": ref.group(1) if ref else "",
            }
        )

    return {"edges": edges, "segments": segments, "vias": vias, "pads": pads}


def bounds(board: dict[str, Any]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for x1, y1, x2, y2 in board["edges"]:
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    for seg in board["segments"]:
        xs.extend([seg["x1"], seg["x2"]])
        ys.extend([seg["y1"], seg["y2"]])
    for pad in board["pads"]:
        xs.extend([pad["x"] - pad["sx"], pad["x"] + pad["sx"]])
        ys.extend([pad["y"] - pad["sy"], pad["y"] + pad["sy"]])
    if not xs or not ys:
        return 0.0, 0.0, 10.0, 10.0
    margin = max(0.5, 0.04 * max(max(xs) - min(xs), max(ys) - min(ys)))
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def render(board: dict[str, Any], output: Path, title: str) -> None:
    x_min, y_min, x_max, y_max = bounds(board)
    width = max(x_max - x_min, 1.0)
    height = max(y_max - y_min, 1.0)
    fig_w = 14
    fig_h = max(4, min(10, fig_w * height / width))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_facecolor("#f8fafc")

    for x1, y1, x2, y2 in board["edges"]:
        ax.plot([x1, x2], [y1, y2], color=LAYER_COLORS["Edge.Cuts"], linewidth=1.4, solid_capstyle="round")

    for seg in board["segments"]:
        color = LAYER_COLORS.get(seg["layer"], "#374151")
        ax.plot(
            [seg["x1"], seg["x2"]],
            [seg["y1"], seg["y2"]],
            color=color,
            linewidth=max(seg["width"] * 22, 1.2),
            alpha=0.88,
            solid_capstyle="round",
        )

    for pad in board["pads"]:
        color = "#dc2626" if pad["ref"].startswith("A") else "#2563eb" if pad["ref"].startswith("B") else "#111827"
        if pad["shape"] == "circle":
            ax.add_patch(Circle((pad["x"], pad["y"]), max(pad["sx"], pad["sy"]) / 2, color=color, alpha=0.92))
        else:
            ax.add_patch(
                Rectangle(
                    (pad["x"] - pad["sx"] / 2, pad["y"] - pad["sy"] / 2),
                    pad["sx"],
                    pad["sy"],
                    color=color,
                    alpha=0.92,
                )
            )

    for via in board["vias"]:
        ax.add_patch(Circle((via["x"], via["y"]), via["size"] / 2, fill=False, edgecolor="#9333ea", linewidth=1.2))

    ax.set_title(title, fontsize=13, weight="bold")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_max, y_min)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linewidth=0.25, alpha=0.45)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def update_manifest(manifest_path: Path, preview_path: Path, summary: dict[str, Any]) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {}
    artifacts = manifest.setdefault("artifacts", {})
    artifacts["kicad_layout_preview_png"] = str(preview_path)
    artifacts["kicad_layout_preview_summary"] = str(preview_path.with_suffix(".json"))
    manifest.setdefault("validation", {})["layout_preview_generated"] = True
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    preview_path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a portable top-down KiCad PCB/package layout preview PNG.")
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    board_path = args.board.resolve()
    if not board_path.exists():
        raise FileNotFoundError(board_path)
    output = args.output.resolve()
    board = parse_board(board_path)
    title = args.title or board_path.name
    render(board, output, title)
    summary = {
        "board": str(board_path),
        "preview_png": str(output),
        "segment_count": len(board["segments"]),
        "pad_count": len(board["pads"]),
        "via_count": len(board["vias"]),
        "edge_count": len(board["edges"]),
        "renderer": "portable_kicad_pcb_parser_matplotlib",
        "note": "Review aid only. Use KiCad DRC and geometry gates for signoff.",
    }
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.manifest:
        update_manifest(args.manifest.resolve(), output, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
