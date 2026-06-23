from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def db20(value: complex) -> float:
    return 20 * math.log10(max(abs(value), 1e-300))


def db10_power(values: list[complex]) -> float:
    return 10 * math.log10(max(sum(abs(v) ** 2 for v in values), 1e-300))


def parse_touchstone(path: Path) -> tuple[list[float], list[list[list[complex]]], str]:
    match = re.search(r"\.s(\d+)p$", path.name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot infer port count from {path}")
    ports = int(match.group(1))
    option = ""
    scale = 1.0
    fmt = "MA"
    nums: list[float] = []
    freqs: list[float] = []
    mats: list[list[list[complex]]] = []
    values_per = 1 + 2 * ports * ports
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("!")[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            option = line
            parts = line.upper().split()
            if "HZ" in parts:
                scale = 1e-9
            elif "KHZ" in parts:
                scale = 1e-6
            elif "MHZ" in parts:
                scale = 1e-3
            elif "GHZ" in parts:
                scale = 1.0
            if "RI" in parts:
                fmt = "RI"
            elif "DB" in parts:
                fmt = "DB"
            else:
                fmt = "MA"
            continue
        nums.extend(float(tok) for tok in line.split())
        while len(nums) >= values_per:
            block = nums[:values_per]
            nums = nums[values_per:]
            freqs.append(block[0] * scale)
            values = block[1:]
            mat = [[0j for _ in range(ports)] for _ in range(ports)]
            idx = 0
            # Touchstone 1.0 n-port data is ordered by source column:
            # S11, S21, ..., SN1, S12, S22, ..., SN2, ...
            for c in range(ports):
                for r in range(ports):
                    a, b = values[idx], values[idx + 1]
                    idx += 2
                    if fmt == "RI":
                        mat[r][c] = complex(a, b)
                    elif fmt == "DB":
                        mat[r][c] = (10 ** (a / 20)) * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
                    else:
                        mat[r][c] = a * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
            mats.append(mat)
    if option.upper().startswith("# HZ") and freqs and max(freqs) < 1e-3:
        # Some PyAEDT/scikit-rf fallback exports label GHz values as Hz.
        # Treat tiny "Hz" values such as 4.0 -> 4 GHz as GHz-domain samples.
        freqs = [f * 1e9 for f in freqs]
        option += "  ! frequency_unit_corrected_from_mislabeled_hz_to_ghz"
    return freqs, mats, option


def z0_from_sii(sii: complex, zref: float = 50.0) -> float:
    denom = 1 - sii
    if abs(denom) < 1e-15:
        return float("inf")
    return abs(zref * (1 + sii) / denom)


def nearest_index(values: list[float], target: float) -> int:
    return min(range(len(values)), key=lambda idx: abs(values[idx] - target))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a multi-lane Touchstone channel.")
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--port-intents", type=Path, required=True)
    parser.add_argument("--data-rate-gbps", type=float, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    parser.add_argument("--loss-limit-db", type=float, default=-7.5)
    parser.add_argument("--xt-limit-db", type=float, default=-25.0)
    parser.add_argument("--z0-target-ohm", type=float, default=50.0)
    parser.add_argument("--z0-tolerance-ohm", type=float, default=10.0)
    args = parser.parse_args()

    freqs, mats, option = parse_touchstone(args.touchstone)
    nyq = args.data_rate_gbps / 2
    stop_required = 5 * nyq
    idx = nearest_index(freqs, nyq)
    mat = mats[idx]
    port_spec = json.loads(args.port_intents.read_text(encoding="utf-8-sig"))
    port_count = len(port_spec.get("ports", []))
    lanes = port_count // 2
    results = []
    for lane in range(lanes):
        near = 2 * lane
        far = near + 1
        il = db20(mat[far][near])
        z_near = z0_from_sii(mat[near][near], args.z0_target_ohm)
        z_far = z0_from_sii(mat[far][far], args.z0_target_ohm)
        xt_terms = []
        xt_ratios = []
        for other in range(lanes):
            if other == lane:
                continue
            other_near = 2 * other
            other_far = other_near + 1
            for label, row in (("NEXT", other_near), ("FEXT", other_far)):
                val = mat[row][near]
                xt_terms.append({"aggressor_lane": other, "kind": label, "db": db20(val)})
                xt_ratios.append(val)
        xt_power = db10_power(xt_ratios)
        worst = max(xt_terms, key=lambda item: item["db"])
        z0_pass = abs(z_near - args.z0_target_ohm) <= args.z0_tolerance_ohm and abs(z_far - args.z0_target_ohm) <= args.z0_tolerance_ohm
        results.append(
            {
                "lane": lane,
                "ports": [near + 1, far + 1],
                "insertion_loss_db": il,
                "loss_limit_db": args.loss_limit_db,
                "loss_pass": il > args.loss_limit_db,
                "xt_power_sum_db": xt_power,
                "xt_limit_db": args.xt_limit_db,
                "xt_pass": xt_power < args.xt_limit_db,
                "worst_single_xt": worst,
                "z0_proxy_near_ohm": z_near,
                "z0_proxy_far_ohm": z_far,
                "z0_proxy_pass": z0_pass,
                "return_loss_near_db": db20(mat[near][near]),
                "return_loss_far_db": db20(mat[far][far]),
            }
        )
    payload = {
        "touchstone": str(args.touchstone),
        "option": option,
        "port_count": port_count,
        "lane_count": lanes,
        "frequency_points_ghz": freqs,
        "nyquist_ghz": nyq,
        "required_stop_ghz": stop_required,
        "actual_stop_ghz": max(freqs) if freqs else None,
        "sample_frequency_ghz": freqs[idx],
        "results": results,
        "pass_fail": {
            "frequency_range": bool(freqs and max(freqs) >= stop_required),
            "loss": all(item["loss_pass"] for item in results),
            "crosstalk": all(item["xt_pass"] for item in results),
            "z0_proxy": all(item["z0_proxy_pass"] for item in results),
        },
        "notes": [
            "Loss and crosstalk are evaluated at the nearest solved sample to Nyquist.",
            "Crosstalk is power-summed over all other receiver-side and transmitter-side coupled terms available in the S-parameter matrix.",
            "Z0 proxy is derived from Sii with a 50 ohm reference; a dedicated 2D/field-solver impedance extraction remains the stronger evidence for characteristic impedance.",
        ],
    }
    payload["pass_fail"]["overall"] = all(payload["pass_fail"].values())
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Multi-Lane Touchstone Channel Check",
        "",
        f"- Touchstone: `{args.touchstone}`",
        f"- Ports / lanes: {port_count} / {lanes}",
        f"- Nyquist: {nyq:g} GHz; required stop: {stop_required:g} GHz; actual stop: {payload['actual_stop_ghz']:g} GHz",
        f"- Overall: {payload['pass_fail']['overall']}",
        "",
        "| Lane | IL dB | IL pass | XT power dB | XT pass | Z0 near | Z0 far | Z0 pass | Worst XT |",
        "|---:|---:|:---:|---:|:---:|---:|---:|:---:|---|",
    ]
    for item in results:
        worst = item["worst_single_xt"]
        lines.append(
            f"| {item['lane']} | {item['insertion_loss_db']:.3f} | {item['loss_pass']} | "
            f"{item['xt_power_sum_db']:.3f} | {item['xt_pass']} | "
            f"{item['z0_proxy_near_ohm']:.2f} | {item['z0_proxy_far_ohm']:.2f} | {item['z0_proxy_pass']} | "
            f"L{worst['aggressor_lane']} {worst['kind']} {worst['db']:.2f} dB |"
        )
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["pass_fail"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
