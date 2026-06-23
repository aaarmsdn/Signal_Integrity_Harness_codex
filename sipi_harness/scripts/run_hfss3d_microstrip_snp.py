from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path

from ansys.aedt.core import Hfss


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve a 2-port HFSS 3D microstrip and export Touchstone.")
    parser.add_argument("--output-dir", default=str(Path("..") / "outputs" / "hfss_microstrip_s21"))
    parser.add_argument("--project-prefix", default="microstrip_50ohm_fr4_1p6_hfss3d")
    parser.add_argument("--design", default="Microstrip_50ohm_FR4_1p6")
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--line-length-mm", type=float, default=70.0)
    parser.add_argument("--line-width-mm", type=float, default=2.986)
    parser.add_argument("--substrate-height-mm", type=float, default=1.6)
    parser.add_argument("--substrate-width-mm", type=float, default=40.0)
    parser.add_argument("--copper-thickness-mm", type=float, default=0.035)
    parser.add_argument("--start-ghz", type=float, default=0.1)
    parser.add_argument("--stop-ghz", type=float, default=10.0)
    parser.add_argument("--points", type=int, default=21)
    parser.add_argument("--adaptive-ghz", type=float, default=5.0)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--impedance", type=float, default=50.0)
    parser.add_argument("--setup", default="Setup1")
    parser.add_argument("--sweep", default="Sweep1")
    return parser.parse_args()


def mm(value: float) -> str:
    return f"{value:g}mm"


def parse_s21(s2p_path: Path, csv_path: Path) -> None:
    rows = []
    freq_scale = 1.0
    data_format = "ma"
    for raw_line in s2p_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            tokens = line[1:].lower().split()
            if tokens and tokens[0] == "hz":
                freq_scale = 1e-9
            elif tokens and tokens[0] == "mhz":
                freq_scale = 1e-3
            elif tokens and tokens[0] == "ghz":
                freq_scale = 1.0
            for token in tokens:
                if token in {"ma", "db", "ri"}:
                    data_format = token
            continue
        vals = [float(x) for x in line.split()]
        if len(vals) < 9:
            continue
        freq_ghz = vals[0] * freq_scale
        a, b = vals[3], vals[4]
        if data_format == "db":
            s21_db = a
            s21_mag = 10 ** (a / 20)
            phase = b
        elif data_format == "ri":
            s21_mag = math.hypot(a, b)
            s21_db = 20 * math.log10(s21_mag) if s21_mag > 0 else -999.0
            phase = math.degrees(math.atan2(b, a))
        else:
            s21_mag = a
            s21_db = 20 * math.log10(s21_mag) if s21_mag > 0 else -999.0
            phase = b
        rows.append({"freq_ghz": freq_ghz, "s21_db": s21_db, "s21_mag": s21_mag, "s21_phase_deg": phase})
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["freq_ghz", "s21_db", "s21_mag", "s21_phase_deg"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    project = out_dir / f"{args.project_prefix}_{run_id}.aedt"
    s2p = out_dir / f"{args.project_prefix}_{run_id}.s2p"
    csv_path = out_dir / f"{args.project_prefix}_{run_id}_s21.csv"
    summary_path = out_dir / f"{args.project_prefix}_{run_id}_summary.json"

    hfss = Hfss(
        project=str(project),
        design=args.design,
        solution_type="Modal",
        version=args.version,
        non_graphical=args.non_graphical,
        new_desktop=False,
        close_on_exit=False,
    )
    try:
        hfss.modeler.model_units = "mm"
        half_l = args.line_length_mm / 2
        copper_t = args.copper_thickness_mm

        ground = hfss.modeler.create_box(
            origin=[mm(-half_l), mm(-args.substrate_width_mm / 2), mm(-copper_t)],
            sizes=[mm(args.line_length_mm), mm(args.substrate_width_mm), mm(copper_t)],
            name="gnd",
            material="copper",
        )
        hfss.modeler.create_box(
            origin=[mm(-half_l), mm(-args.substrate_width_mm / 2), "0mm"],
            sizes=[mm(args.line_length_mm), mm(args.substrate_width_mm), mm(args.substrate_height_mm)],
            name="substrate",
            material="FR4_epoxy",
        )
        trace = hfss.modeler.create_box(
            origin=[mm(-half_l), mm(-args.line_width_mm / 2), mm(args.substrate_height_mm)],
            sizes=[mm(args.line_length_mm), mm(args.line_width_mm), mm(copper_t)],
            name="trace",
            material="copper",
        )
        hfss.create_open_region(frequency=f"{args.stop_ghz:g}GHz", boundary="Radiation", apply_infinite_ground=False)

        z_mid = args.substrate_height_mm + copper_t / 2
        port_height = args.substrate_height_mm + 2 * copper_t
        p1_sheet = hfss.modeler.create_rectangle(
            "YZ",
            [mm(-half_l), mm(-args.substrate_width_mm / 2), mm(-copper_t)],
            [mm(args.substrate_width_mm), mm(port_height)],
            name="P1_sheet",
            material="vacuum",
        )
        p2_sheet = hfss.modeler.create_rectangle(
            "YZ",
            [mm(half_l), mm(-args.substrate_width_mm / 2), mm(-copper_t)],
            [mm(args.substrate_width_mm), mm(port_height)],
            name="P2_sheet",
            material="vacuum",
        )

        hfss.lumped_port(
            assignment=p1_sheet.name,
            create_port_sheet=False,
            integration_line=[[-half_l, 0, z_mid], [-half_l, 0, 0]],
            impedance=args.impedance,
            name="P1",
            renormalize=True,
        )
        hfss.lumped_port(
            assignment=p2_sheet.name,
            create_port_sheet=False,
            integration_line=[[half_l, 0, z_mid], [half_l, 0, 0]],
            impedance=args.impedance,
            name="P2",
            renormalize=True,
        )

        setup = hfss.create_setup(name=args.setup)
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
        solved = bool(hfss.analyze_setup(args.setup))
        exported = hfss.export_touchstone(
            setup=args.setup,
            sweep=args.sweep,
            output_file=str(s2p),
            renormalization=True,
            impedance=args.impedance,
        )
        if exported:
            parse_s21(Path(exported), csv_path)
        summary = {
            "ok": bool(solved and exported),
            "project": str(project),
            "design": args.design,
            "touchstone": str(exported) if exported else False,
            "s21_csv": str(csv_path) if exported else False,
            "ports": hfss.get_all_sources(),
            "parameters": vars(args),
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    finally:
        hfss.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    main()
