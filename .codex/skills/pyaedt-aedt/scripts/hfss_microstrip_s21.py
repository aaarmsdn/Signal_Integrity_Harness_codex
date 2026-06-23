#!/usr/bin/env python3
"""Create and optionally solve an HFSS microstrip line S21 extraction.

This script is intended for Codex/PyAEDT automation. It creates a new AEDT
project by default so repeated agent runs do not overwrite prior work.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path


def copper_thickness_to_mm(value: str) -> float:
    text = str(value).strip().lower().replace(" ", "")
    if text.endswith("oz"):
        return float(text[:-2]) * 0.0348
    if text.endswith("um"):
        return float(text[:-2]) / 1000.0
    if text.endswith("mil"):
        return float(text[:-3]) * 0.0254
    if text.endswith("mm"):
        return float(text[:-2])
    return float(text)


def mm(value: float) -> str:
    return f"{value:g}mm"


def face_at_x(obj, x_mm: float):
    faces = getattr(obj, "faces", None)
    if not faces:
        raise RuntimeError(f"Object {getattr(obj, 'name', obj)} has no accessible faces.")

    def distance(face):
        center = getattr(face, "center", None)
        if center is None:
            return float("inf")
        return abs(float(center[0]) - x_mm)

    return min(faces, key=distance)


def parse_touchstone_s21_to_csv(s2p_path: Path, csv_path: Path) -> None:
    unit_scale_to_ghz = {
        "hz": 1e-9,
        "khz": 1e-6,
        "mhz": 1e-3,
        "ghz": 1.0,
    }
    freq_scale = 1.0
    data_format = "ma"
    rows = []

    for raw_line in s2p_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            tokens = line[1:].lower().split()
            if tokens:
                freq_scale = unit_scale_to_ghz.get(tokens[0], freq_scale)
            for token in tokens:
                if token in {"ma", "db", "ri"}:
                    data_format = token
            continue
        values = [float(x) for x in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", line)]
        if len(values) < 9:
            continue
        freq_ghz = values[0] * freq_scale
        a = values[3]
        b = values[4]
        if data_format == "db":
            s21_db = a
            s21_mag = 10 ** (a / 20.0)
            s21_phase_deg = b
        elif data_format == "ri":
            s21_mag = math.hypot(a, b)
            s21_db = 20.0 * math.log10(s21_mag) if s21_mag > 0 else -999.0
            s21_phase_deg = math.degrees(math.atan2(b, a))
        else:
            s21_mag = a
            s21_db = 20.0 * math.log10(s21_mag) if s21_mag > 0 else -999.0
            s21_phase_deg = b
        rows.append(
            {
                "freq_ghz": freq_ghz,
                "s21_db": s21_db,
                "s21_mag": s21_mag,
                "s21_phase_deg": s21_phase_deg,
            }
        )

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["freq_ghz", "s21_db", "s21_mag", "s21_phase_deg"])
        writer.writeheader()
        writer.writerows(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HFSS microstrip S21 automation through PyAEDT.")
    parser.add_argument("--output-dir", default="outputs/hfss_microstrip_s21")
    parser.add_argument("--project-prefix", default="microstrip_s21")
    parser.add_argument("--design", default="Microstrip_S21")
    parser.add_argument("--version", default=None, help="AEDT version, for example 2026.1. Omit to use active/latest.")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--new-desktop", action="store_true")
    parser.add_argument("--remove-lock", action="store_true")
    parser.add_argument("--close-desktop", action="store_true")

    parser.add_argument("--line-length-mm", type=float, default=50.0)
    parser.add_argument("--line-width-mm", type=float, default=5.0)
    parser.add_argument("--substrate-height-mm", type=float, default=3.0)
    parser.add_argument("--substrate-width-mm", type=float, default=30.0)
    parser.add_argument("--copper-thickness", default="1oz")
    parser.add_argument("--substrate-material", default="FR4_epoxy")

    parser.add_argument("--start-ghz", type=float, default=0.1)
    parser.add_argument("--stop-ghz", type=float, default=10.0)
    parser.add_argument("--points", type=int, default=201)
    parser.add_argument("--adaptive-ghz", type=float, default=5.0)
    parser.add_argument("--max-passes", type=int, default=8)
    parser.add_argument("--impedance", type=float, default=50.0)

    parser.add_argument("--setup", default="Setup1")
    parser.add_argument("--sweep", default="Sweep1")
    parser.add_argument("--run-solve", action="store_true", help="Actually run HFSS and export results.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_path = out_dir / f"{args.project_prefix}_{run_id}.aedt"
    s2p_path = out_dir / f"{args.project_prefix}_{run_id}.s2p"
    s21_csv_path = out_dir / f"{args.project_prefix}_{run_id}_s21.csv"
    summary_path = out_dir / f"{args.project_prefix}_{run_id}_summary.json"

    copper_t_mm = copper_thickness_to_mm(args.copper_thickness)
    half_l = args.line_length_mm / 2.0

    from ansys.aedt.core import Hfss

    hfss = Hfss(
        project=str(project_path),
        design=args.design,
        solution_type="Modal",
        version=args.version,
        non_graphical=args.non_graphical,
        new_desktop=args.new_desktop,
        close_on_exit=False,
        remove_lock=args.remove_lock,
    )
    hfss.modeler.model_units = "mm"

    hfss["line_len"] = mm(args.line_length_mm)
    hfss["line_w"] = mm(args.line_width_mm)
    hfss["sub_h"] = mm(args.substrate_height_mm)
    hfss["sub_w"] = mm(args.substrate_width_mm)
    hfss["cu_t"] = mm(copper_t_mm)

    ground = hfss.modeler.create_box(
        origin=["-line_len/2", "-sub_w/2", "-cu_t"],
        sizes=["line_len", "sub_w", "cu_t"],
        name="gnd",
        material="copper",
    )
    substrate = hfss.modeler.create_box(
        origin=["-line_len/2", "-sub_w/2", "0mm"],
        sizes=["line_len", "sub_w", "sub_h"],
        name="substrate",
        material=args.substrate_material,
    )
    trace = hfss.modeler.create_box(
        origin=["-line_len/2", "-line_w/2", "sub_h"],
        sizes=["line_len", "line_w", "cu_t"],
        name="trace",
        material="copper",
    )

    hfss.create_open_region(frequency=f"{args.stop_ghz:g}GHz", boundary="Radiation", apply_infinite_ground=False)

    hfss.lumped_port(
        assignment=ground.name,
        reference=trace.name,
        create_port_sheet=True,
        integration_line=hfss.axis_directions.XNeg,
        impedance=args.impedance,
        name="P1",
        renormalize=True,
    )
    hfss.lumped_port(
        assignment=ground.name,
        reference=trace.name,
        create_port_sheet=True,
        integration_line=hfss.axis_directions.XPos,
        impedance=args.impedance,
        name="P2",
        renormalize=True,
    )

    setup = hfss.create_setup(name=args.setup)
    if hasattr(setup, "props"):
        setup.props["Frequency"] = f"{args.adaptive_ghz:g}GHz"
        setup.props["MaximumPasses"] = args.max_passes
        setup.update()

    hfss.create_linear_count_sweep(
        setup=args.setup,
        unit="GHz",
        start_frequency=args.start_ghz,
        stop_frequency=args.stop_ghz,
        num_of_freq_points=args.points,
        name=args.sweep,
    )

    hfss.save_project()

    exported_touchstone = None
    exported_s21_csv = None
    if args.run_solve:
        hfss.analyze_setup(args.setup)
        exported_touchstone = hfss.export_touchstone(
            setup=args.setup,
            sweep=args.sweep,
            output_file=str(s2p_path),
            renormalization=True,
            impedance=args.impedance,
        )
        if exported_touchstone:
            parse_touchstone_s21_to_csv(Path(exported_touchstone), s21_csv_path)
            exported_s21_csv = str(s21_csv_path)

    summary = {
        "status": "ok",
        "project": str(project_path),
        "design": args.design,
        "ran_solve": bool(args.run_solve),
        "touchstone": exported_touchstone,
        "s21_csv": exported_s21_csv,
        "parameters": {
            "line_length_mm": args.line_length_mm,
            "line_width_mm": args.line_width_mm,
            "substrate_height_mm": args.substrate_height_mm,
            "substrate_width_mm": args.substrate_width_mm,
            "copper_thickness_mm": copper_t_mm,
            "substrate_material": args.substrate_material,
            "start_ghz": args.start_ghz,
            "stop_ghz": args.stop_ghz,
            "points": args.points,
            "impedance": args.impedance,
        },
        "methods": [
            "ansys.aedt.core.hfss.Hfss",
            "ansys.aedt.core.hfss.Hfss.lumped_port",
            "ansys.aedt.core.hfss.Hfss.create_open_region",
            "ansys.aedt.core.hfss.Hfss.create_setup",
            "ansys.aedt.core.hfss.Hfss.create_linear_count_sweep",
            "ansys.aedt.core.hfss.Hfss.export_touchstone",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if args.close_desktop:
        hfss.release_desktop(close_projects=True, close_desktop=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
