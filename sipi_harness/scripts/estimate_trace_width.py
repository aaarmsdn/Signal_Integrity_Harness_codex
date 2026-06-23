from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def microstrip_z0_ohm(width_mm: float, height_mm: float, er: float, copper_thickness_mm: float) -> float:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("width_mm and height_mm must be positive")
    return 87.0 / math.sqrt(er + 1.41) * math.log((5.98 * height_mm) / (0.8 * width_mm + copper_thickness_mm))


def estimate_microstrip_width_mm(
    target_ohm: float,
    height_mm: float,
    er: float,
    copper_thickness_mm: float,
) -> float:
    low = 0.001
    high = max(height_mm * 5.0, 0.5)
    while microstrip_z0_ohm(high, height_mm, er, copper_thickness_mm) > target_ohm and high < 20.0:
        high *= 2.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if microstrip_z0_ohm(mid, height_mm, er, copper_thickness_mm) > target_ohm:
            low = mid
        else:
            high = mid
    return round(high, 6)


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate pre-layout trace width from target impedance.")
    parser.add_argument("--target-ohm", type=float, required=True)
    parser.add_argument("--er", type=float, required=True)
    parser.add_argument("--height-mm", type=float, required=True, help="Dielectric height to the reference plane.")
    parser.add_argument("--copper-thickness-mm", type=float, default=0.018)
    parser.add_argument("--pitch-mm", type=float, default=None)
    parser.add_argument("--clearance-mm", type=float, default=None)
    parser.add_argument("--max-width-mm", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    estimated_width = estimate_microstrip_width_mm(
        args.target_ohm,
        args.height_mm,
        args.er,
        args.copper_thickness_mm,
    )
    max_width = args.max_width_mm
    if max_width is None and args.pitch_mm is not None and args.clearance_mm is not None:
        max_width = max(0.001, args.pitch_mm - 2.0 * args.clearance_mm)
    applied_width = min(estimated_width, max_width) if max_width is not None else estimated_width
    applied_z0 = microstrip_z0_ohm(applied_width, args.height_mm, args.er, args.copper_thickness_mm)

    result = {
        "model": "single_ended_microstrip_ipc2141_rough_pre_layout",
        "target_impedance_ohm": args.target_ohm,
        "er": args.er,
        "height_mm": args.height_mm,
        "copper_thickness_mm": args.copper_thickness_mm,
        "estimated_width_mm": estimated_width,
        "applied_width_mm": round(applied_width, 6),
        "applied_estimated_z0_ohm": round(applied_z0, 3),
        "max_width_mm": max_width,
        "status": "estimated_from_target" if applied_width == estimated_width else "estimated_clamped_by_geometry",
        "evidence_status": "pre_layout_proxy_requires_field_solver_or_measurement",
    }
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
