from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any


UNIT_TO_GHZ = {
    "HZ": 1e-9,
    "KHZ": 1e-6,
    "MHZ": 1e-3,
    "GHZ": 1.0,
}


def infer_port_count(path: Path) -> int:
    match = re.search(r"\.s(\d+)p$", path.name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot infer Touchstone port count from extension: {path}")
    return int(match.group(1))


def parse_option(line: str) -> dict[str, Any]:
    tokens = line.strip().split()
    if not tokens or tokens[0] != "#":
        raise ValueError(f"Invalid Touchstone option line: {line!r}")
    upper = [token.upper() for token in tokens]
    option = {
        "unit": upper[1] if len(upper) > 1 else "GHZ",
        "parameter": upper[2] if len(upper) > 2 else "S",
        "format": upper[3] if len(upper) > 3 else "MA",
        "zref": 50.0,
        "raw": line.strip(),
    }
    if "R" in upper:
        idx = upper.index("R")
        if idx + 1 < len(tokens):
            option["zref"] = float(tokens[idx + 1])
    if option["parameter"] != "S":
        raise ValueError(f"Only S-parameter Touchstone files are supported, got {option['parameter']}")
    if option["format"] not in {"RI", "MA", "DB"}:
        raise ValueError(f"Unsupported Touchstone data format: {option['format']}")
    return option


def pair_to_complex(a: float, b: float, fmt: str) -> complex:
    if fmt == "RI":
        return complex(a, b)
    if fmt == "MA":
        angle = math.radians(b)
        return complex(a * math.cos(angle), a * math.sin(angle))
    if fmt == "DB":
        mag = 10 ** (a / 20.0)
        angle = math.radians(b)
        return complex(mag * math.cos(angle), mag * math.sin(angle))
    raise ValueError(f"Unsupported Touchstone data format: {fmt}")


def read_touchstone_flat(path: Path) -> dict[str, Any]:
    nports = infer_port_count(path)
    values_per_frequency = 1 + 2 * nports * nports
    option_line = "# GHZ S MA R 50"
    comments: list[str] = []
    numeric: list[float] = []
    freqs_ghz: list[float] = []
    rows: list[list[complex]] = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("!"):
            comments.append(raw.rstrip())
            continue
        if line.startswith("#"):
            option_line = line
            continue
        payload = raw.split("!")[0].strip()
        if payload:
            numeric.extend(float(token) for token in payload.split())
        option = parse_option(option_line)
        while len(numeric) >= values_per_frequency:
            block = numeric[:values_per_frequency]
            numeric = numeric[values_per_frequency:]
            freqs_ghz.append(block[0] * UNIT_TO_GHZ.get(option["unit"], 1.0))
            values = block[1:]
            row = [
                pair_to_complex(values[idx], values[idx + 1], option["format"])
                for idx in range(0, len(values), 2)
            ]
            rows.append(row)

    if not freqs_ghz:
        raise ValueError(f"No Touchstone data rows found in {path}")
    if len(freqs_ghz) != len(rows):
        raise ValueError(f"Frequency/value row mismatch in {path}")
    if any(len(row) != nports * nports for row in rows):
        raise ValueError(f"Touchstone row width mismatch in {path}")
    order = sorted(range(len(freqs_ghz)), key=lambda idx: freqs_ghz[idx])
    return {
        "nports": nports,
        "option": parse_option(option_line),
        "comments": comments,
        "freqs_ghz": [freqs_ghz[idx] for idx in order],
        "rows": [rows[idx] for idx in order],
    }


def interpolate_row(
    target_ghz: float,
    freqs_ghz: list[float],
    rows: list[list[complex]],
    cursor: int,
) -> tuple[list[complex], int]:
    if target_ghz <= freqs_ghz[0]:
        return rows[0], 0
    if target_ghz >= freqs_ghz[-1]:
        return rows[-1], len(freqs_ghz) - 2
    idx = min(max(cursor, 0), len(freqs_ghz) - 2)
    while idx < len(freqs_ghz) - 2 and freqs_ghz[idx + 1] < target_ghz:
        idx += 1
    while idx > 0 and freqs_ghz[idx] > target_ghz:
        idx -= 1
    f0 = freqs_ghz[idx]
    f1 = freqs_ghz[idx + 1]
    if f1 <= f0:
        return rows[idx], idx
    alpha = (target_ghz - f0) / (f1 - f0)
    row = [v0 + (v1 - v0) * alpha for v0, v1 in zip(rows[idx], rows[idx + 1])]
    return row, idx


def build_grid(start_ghz: float, stop_ghz: float, max_step_ghz: float, min_points: int) -> list[float]:
    if stop_ghz <= start_ghz:
        return [start_ghz]
    intervals = max(1, min_points - 1, math.ceil((stop_ghz - start_ghz) / max_step_ghz))
    step = (stop_ghz - start_ghz) / intervals
    return [start_ghz + idx * step for idx in range(intervals)] + [stop_ghz]


def write_touchstone_ri(path: Path, data: dict[str, Any], freqs_ghz: list[float], rows: list[list[complex]]) -> None:
    zref = float(data["option"].get("zref", 50.0))
    nports = int(data["nports"])
    lines = [
        "! Generated by resample_touchstone_for_eye.py",
        "! Purpose: dense RI-domain interpolation for ADS ChannelSim eye/BER analysis",
        f"! Source option: {data['option'].get('raw', '')}",
    ]
    for comment in data.get("comments", []):
        if comment.lower().startswith("! port["):
            lines.append(comment)
    lines.append(f"# GHZ S RI R {zref:g}")
    for freq_ghz, row in zip(freqs_ghz, rows):
        flat = [freq_ghz]
        for value in row:
            flat.extend([value.real, value.imag])
        first_count = 1 + 2 * nports
        lines.append(" ".join(f"{value:.12g}" for value in flat[:first_count]))
        continuation_values = flat[first_count:]
        continuation_count = 2 * nports
        for start in range(0, len(continuation_values), continuation_count):
            chunk = continuation_values[start : start + continuation_count]
            lines.append(" " + " ".join(f"{value:.12g}" for value in chunk))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def preprocess_touchstone_for_eye(
    input_path: Path,
    output_dir: Path,
    data_rate_gbps: float,
    max_step_ghz: float | None = None,
    min_points: int = 101,
    force: bool = False,
    output_name: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    data = read_touchstone_flat(input_path)
    freqs = data["freqs_ghz"]
    nyquist_ghz = data_rate_gbps / 2.0
    default_step = max(0.001, min(0.05, nyquist_ghz / 40.0))
    step_limit = max_step_ghz if max_step_ghz is not None else default_step
    deltas = [b - a for a, b in zip(freqs, freqs[1:])]
    max_delta = max(deltas) if deltas else float("inf")
    sparse = force or len(freqs) < min_points or max_delta > step_limit
    output_path = input_path
    summary = {
        "schema_version": "touchstone_eye_interpolation_v1",
        "input": str(input_path),
        "output": str(input_path),
        "data_rate_gbps": data_rate_gbps,
        "nyquist_ghz": nyquist_ghz,
        "point_count_in": len(freqs),
        "point_count_out": len(freqs),
        "frequency_range_ghz": [min(freqs), max(freqs)],
        "max_step_ghz": max_delta if math.isfinite(max_delta) else None,
        "step_limit_ghz": step_limit,
        "min_points": min_points,
        "resampled": False,
        "reason": "input_grid_accepted",
        "method": "complex_linear_interpolation_in_RI_domain",
    }
    if sparse:
        output_dir.mkdir(parents=True, exist_ok=True)
        name = output_name or f"{input_path.stem}_eye_interp{input_path.suffix}"
        output_path = output_dir / name
        new_freqs = build_grid(min(freqs), max(freqs), step_limit, min_points)
        cursor = 0
        new_rows: list[list[complex]] = []
        for freq in new_freqs:
            row, cursor = interpolate_row(freq, freqs, data["rows"], cursor)
            new_rows.append(row)
        write_touchstone_ri(output_path, data, new_freqs, new_rows)
        summary.update(
            {
                "output": str(output_path),
                "point_count_out": len(new_freqs),
                "max_step_out_ghz": max(b - a for a, b in zip(new_freqs, new_freqs[1:])) if len(new_freqs) > 1 else None,
                "resampled": True,
                "reason": "input_grid_sparse_for_eye_channel_sim",
            }
        )
    elif input_path.parent.resolve() != output_dir.resolve():
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / input_path.name
        if input_path.resolve() != output_path.resolve():
            shutil.copy2(input_path, output_path)
            summary["output"] = str(output_path)
    return output_path, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Resample sparse Touchstone files before ADS ChannelSim eye simulation.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-rate-gbps", type=float, required=True)
    parser.add_argument("--max-step-ghz", type=float)
    parser.add_argument("--min-points", type=int, default=101)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-name")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    output, summary = preprocess_touchstone_for_eye(
        args.input,
        args.output_dir,
        args.data_rate_gbps,
        max_step_ghz=args.max_step_ghz,
        min_points=args.min_points,
        force=args.force,
        output_name=args.output_name,
    )
    summary["output"] = str(output)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
