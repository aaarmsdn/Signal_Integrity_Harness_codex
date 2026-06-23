from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


PORT_RE = re.compile(r"DATA(?P<lane>\d+).*?(?P<side>TX|RX)", re.IGNORECASE)


def parse_option(line: str) -> dict[str, object]:
    tokens = line.strip().split()
    if not tokens or tokens[0] != "#":
        raise ValueError(f"Invalid Touchstone option line: {line!r}")
    upper = [t.upper() for t in tokens]
    unit = upper[1] if len(upper) > 1 else "HZ"
    parameter = upper[2] if len(upper) > 2 else "S"
    fmt = upper[3] if len(upper) > 3 else "MA"
    zref = 50.0
    if "R" in upper:
        idx = upper.index("R")
        if idx + 1 < len(tokens):
            zref = float(tokens[idx + 1])
    return {"unit": unit, "parameter": parameter, "format": fmt, "zref": zref}


def unit_to_hz(unit: str) -> float:
    return {
        "HZ": 1.0,
        "KHZ": 1e3,
        "MHZ": 1e6,
        "GHZ": 1e9,
    }.get(unit.upper(), 1.0)


def complex_from_pair(a: float, b: float, fmt: str) -> complex:
    fmt = fmt.upper()
    if fmt == "RI":
        return complex(a, b)
    if fmt == "MA":
        angle = math.radians(b)
        return complex(a * math.cos(angle), a * math.sin(angle))
    if fmt == "DB":
        mag = 10 ** (a / 20.0)
        angle = math.radians(b)
        return complex(mag * math.cos(angle), mag * math.sin(angle))
    raise ValueError(f"Unsupported Touchstone format: {fmt}")


def pair_from_complex(value: complex) -> tuple[float, float]:
    return abs(value), math.degrees(math.atan2(value.imag, value.real))


def read_touchstone(path: Path) -> dict[str, object]:
    nports = int(path.suffix.lower().removeprefix(".s").removesuffix("p"))
    per_frequency_values = 1 + 2 * nports * nports
    option_line = "# GHZ S MA R 50"
    comments: list[str] = []
    ports: list[str | None] = [None] * nports
    numeric: list[float] = []
    rows: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("!"):
            comments.append(raw.rstrip())
            match = re.match(r"!\s*Port\[(\d+)\]\s*=\s*(.+)", line, re.IGNORECASE)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < nports:
                    ports[idx] = match.group(2).strip()
            continue
        if line.startswith("#"):
            option_line = line
            continue
        numeric.extend(float(item) for item in line.split())
        while len(numeric) >= per_frequency_values:
            chunk = numeric[:per_frequency_values]
            numeric = numeric[per_frequency_values:]
            rows.append({"frequency": chunk[0], "values": chunk[1:]})
    option = parse_option(option_line)
    matrices = []
    fmt = str(option["format"])
    for row in rows:
        matrix = [[0j for _ in range(nports)] for _ in range(nports)]
        values = row["values"]
        idx = 0
        for r in range(nports):
            for c in range(nports):
                matrix[r][c] = complex_from_pair(float(values[idx]), float(values[idx + 1]), fmt)
                idx += 2
        matrices.append({"frequency": row["frequency"], "matrix": matrix})
    return {
        "nports": nports,
        "option": option,
        "comments": comments,
        "ports": ports,
        "matrices": matrices,
    }


def infer_txrx_order(ports: list[str | None], lane_count: int | None = None) -> list[int]:
    lanes: dict[int, dict[str, int]] = {}
    for idx, name in enumerate(ports):
        if not name:
            continue
        match = PORT_RE.search(name)
        if not match:
            continue
        lane = int(match.group("lane"))
        side = match.group("side").upper()
        lanes.setdefault(lane, {})[side] = idx
    if lane_count is None:
        lane_count = len(lanes)
    order: list[int] = []
    missing: list[str] = []
    for lane in sorted(lanes)[:lane_count]:
        entry = lanes[lane]
        for side in ("TX", "RX"):
            if side not in entry:
                missing.append(f"DATA{lane:02d}_{side}")
            else:
                order.append(entry[side])
    if missing:
        raise RuntimeError(f"Cannot infer complete TX/RX order; missing: {', '.join(missing)}")
    expected = 2 * lane_count
    if len(order) != expected:
        raise RuntimeError(f"Inferred {len(order)} ports, expected {expected}")
    return order


def write_touchstone(path: Path, data: dict[str, object], order: list[int]) -> None:
    nports = len(order)
    option = data["option"]
    zref = float(option["zref"])
    ports = data["ports"]
    lines = [
        f"! Reordered by reorder_touchstone_ports.py",
        f"! Source port order: {json.dumps(ports)}",
    ]
    for new_idx, old_idx in enumerate(order, start=1):
        lines.append(f"! Port[{new_idx}] = {ports[old_idx] or f'old_port_{old_idx + 1}'}")
    lines.append(f"# {option['unit']} S MA R {zref:g}")
    for row in data["matrices"]:
        matrix = row["matrix"]
        reordered = [[matrix[old_r][old_c] for old_c in order] for old_r in order]
        for r in range(nports):
            values = [float(row["frequency"])] if r == 0 else []
            for c in range(nports):
                mag, angle = pair_from_complex(reordered[r][c])
                values.extend([mag, angle])
            prefix = "" if r == 0 else " "
            lines.append(prefix + " ".join(f"{v:.12g}" for v in values))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reorder a Touchstone file into lane-major TX,RX order using port-name comments."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lane-count", type=int, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args()
    data = read_touchstone(args.input)
    order = infer_txrx_order(data["ports"], args.lane_count)
    write_touchstone(args.output, data, order)
    summary = {
        "ok": True,
        "input": str(args.input),
        "output": str(args.output),
        "lane_count": args.lane_count or len(order) // 2,
        "old_ports": data["ports"],
        "new_ports": [data["ports"][idx] for idx in order],
        "order_1based": [idx + 1 for idx in order],
        "note": "Output order is lane-major TX,RX. Use before ADS benches that expect port pairs as source, receiver.",
    }
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
