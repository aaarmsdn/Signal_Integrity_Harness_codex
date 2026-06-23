from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path

from ansys.aedt.core import Hfss3dLayout


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "outputs" / "hfss3dlayout_import" / "microstrip_50ohm_fr4_1p6_reference_plane_fixed.aedt"
DEFAULT_WORK = ROOT / "outputs" / "hfss3dlayout_import" / "microstrip_50ohm_fr4_1p6_4gbps_oeditor_circuit_padcenter.aedt"
DEFAULT_TOUCHSTONE = ROOT / "outputs" / "hfss3dlayout_import" / "microstrip_50ohm_fr4_1p6_hfss3dlayout_circuit.s2p"
DEFAULT_SUMMARY = ROOT / "outputs" / "hfss3dlayout_import" / "hfss3dlayout_microstrip_oeditor_circuit_summary.json"
DEFAULT_PORT_SPEC = ROOT / "outputs" / "hfss3dlayout_import" / "microstrip_50ohm_fr4_1p6_port_intents.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use HFSS 3D Layout oEditor.CreateCircuitPort for the microstrip coupon.")
    parser.add_argument("--source-project", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--work-project", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--touchstone", type=Path, default=DEFAULT_TOUCHSTONE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--port-spec", type=Path, default=DEFAULT_PORT_SPEC)
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--design", default="PCB")
    parser.add_argument("--setup", default="Setup1")
    parser.add_argument("--sweep", default="Sweep1")
    parser.add_argument("--start-ghz", type=float, default=0.1)
    parser.add_argument("--stop-ghz", type=float, default=10.0)
    parser.add_argument("--points", type=int, default=21)
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-solve", action="store_true")
    return parser.parse_args()


def copy_project(source_project: Path, work_project: Path, overwrite: bool) -> None:
    if not source_project.exists():
        raise FileNotFoundError(source_project)
    source_base = source_project.with_suffix("")
    work_base = work_project.with_suffix("")
    for suffix in [".aedt", ".aedb", ".aedtresults"]:
        src = Path(str(source_base) + suffix)
        dst = Path(str(work_base) + suffix)
        if dst.exists():
            if not overwrite:
                raise FileExistsError(f"{dst} exists; pass --overwrite")
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.exists():
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    lock_file = Path(str(work_project) + ".lock")
    if lock_file.exists():
        lock_file.unlink()


def default_port_spec() -> dict:
    return {
        "schema": "sipi-harness.port-intents.v1",
        "unit": "mm",
        "ports": [
            {
                "name": "Port1",
                "type": "circuit",
                "positive_layer": "f.cu",
                "negative_layer": "b.cu",
                "x": 5.0,
                "y": -20.0,
                "impedance_ohm": 50,
                "role": "tx_or_near_end",
                "net": "SIG_50OHM",
                "reference_net": "GND",
            },
            {
                "name": "Port2",
                "type": "circuit",
                "positive_layer": "f.cu",
                "negative_layer": "b.cu",
                "x": 75.0,
                "y": -20.0,
                "impedance_ohm": 50,
                "role": "rx_or_far_end",
                "net": "SIG_50OHM",
                "reference_net": "GND",
            },
        ],
    }


def load_port_spec(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_port_spec(), indent=2), encoding="utf-8")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if "ports" not in spec or not isinstance(spec["ports"], list):
        raise ValueError(f"Port spec must contain a ports list: {path}")
    return spec


def coordinate_to_meter(value: object, unit: str) -> float:
    scale = {
        "m": 1.0,
        "meter": 1.0,
        "meters": 1.0,
        "mm": 1e-3,
        "millimeter": 1e-3,
        "millimeters": 1e-3,
        "um": 1e-6,
        "mil": 25.4e-6,
    }
    if isinstance(value, (int, float)):
        return float(value) * scale.get(unit, 1.0)
    text = str(value).strip()
    for suffix, factor in sorted(scale.items(), key=lambda item: len(item[0]), reverse=True):
        if text.lower().endswith(suffix):
            return float(text[: -len(suffix)].strip()) * factor
    return float(text) * scale.get(unit, 1.0)


def create_circuit_ports(app: Hfss3dLayout, port_spec: dict) -> list[str]:
    oeditor = app.modeler.oeditor
    existing_ports = list(app.port_list)
    if existing_ports:
        oeditor.Delete(existing_ports)

    unit = port_spec.get("unit", "mm")
    created = []
    for port in port_spec["ports"]:
        if port.get("type", "circuit") != "circuit":
            raise ValueError(f"Unsupported HFSS 3D Layout port type: {port}")
        name = port["name"]
        x = coordinate_to_meter(port["x"], unit)
        y = coordinate_to_meter(port["y"], unit)
        positive_layer = port.get("positive_layer", port.get("pos_layer", "TOP"))
        negative_layer = port.get("negative_layer", port.get("neg_layer", "BOT"))
        before = set(app.port_list)
        oeditor.CreateCircuitPort(
            [
                "NAME:Location",
                "PosLayer:=",
                positive_layer,
                "X0:=",
                x,
                "Y0:=",
                y,
                "NegLayer:=",
                negative_layer,
                "X1:=",
                x,
                "Y1:=",
                y,
            ]
        )
        after = set(app.port_list)
        new_ports = list(after - before)
        if new_ports:
            created.extend(new_ports)
            port["actual_port_name"] = new_ports[0]
    return list(app.port_list)


def ensure_setup(app: Hfss3dLayout, setup_name: str, sweep_name: str, start_ghz: float, stop_ghz: float, points: int) -> None:
    if setup_name not in app.setup_names:
        setup = app.create_setup(
            name=setup_name,
            MeshSizeFactor=2,
            SingleFrequencyDataList__AdaptiveFrequency="5GHz",
        )
    else:
        setup = app.get_setup(setup_name)

    sweep_names = [sweep.name for sweep in setup.sweeps]
    if sweep_name not in sweep_names:
        app.create_linear_count_sweep(
            setup=setup_name,
            unit="GHz",
            start_frequency=start_ghz,
            stop_frequency=stop_ghz,
            num_of_freq_points=points,
            name=sweep_name,
            save_fields=False,
            sweep_type="Discrete",
        )


def main() -> None:
    args = parse_args()
    copy_project(args.source_project, args.work_project, args.overwrite)

    summary = {
        "ok": False,
        "project": str(args.work_project),
        "source_project": str(args.source_project),
        "design": args.design,
        "setup": args.setup,
        "sweep": args.sweep,
        "touchstone": str(args.touchstone),
        "port_policy": {
            "method": "oEditor.CreateCircuitPort",
            "source": str(args.port_spec),
        },
        "attempts": [],
    }

    app = Hfss3dLayout(
        project=str(args.work_project),
        design=args.design,
        version=args.version,
        non_graphical=args.non_graphical,
        new_desktop=True,
        close_on_exit=False,
    )
    try:
        port_spec = load_port_spec(args.port_spec)
        summary["port_spec"] = port_spec
        summary["ports_after_create"] = create_circuit_ports(app, port_spec)
        ensure_setup(app, args.setup, args.sweep, args.start_ghz, args.stop_ghz, args.points)
        app.save_project()
        if not args.skip_solve:
            summary["solved"] = bool(app.analyze_setup(args.setup))
            try:
                exported = app.export_touchstone(
                    setup=args.setup,
                    sweep=args.sweep,
                    output_file=str(args.touchstone),
                    renormalization=True,
                    impedance=50,
                )
                summary["attempts"].append({"method": "export_touchstone", "result": str(exported)})
                summary["touchstone_exists"] = bool(exported and Path(exported).exists())
            except Exception as exc:
                summary["attempts"].append(
                    {
                        "method": "export_touchstone",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
        summary["final_ports"] = app.port_list
        summary["setups"] = app.setup_names
        summary["sweeps"] = app.get_sweeps(args.setup) if args.setup in app.setup_names else []
        summary["ok"] = bool(args.skip_solve or Path(args.touchstone).exists())
        app.save_project()
    finally:
        if args.non_graphical:
            app.release_desktop(close_projects=False, close_desktop=True)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
