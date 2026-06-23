from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import traceback

from ansys.aedt.core import Hfss3dLayout


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Touchstone from a solved HFSS 3D Layout project.")
    parser.add_argument(
        "--project",
        required=True,
        help="Solved AEDT project path.",
    )
    parser.add_argument("--design", default="PCB")
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--setup", default="Setup1")
    parser.add_argument("--sweep", default="Sweep1")
    parser.add_argument(
        "--touchstone",
        required=True,
        help="Output Touchstone path.",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help="Output summary JSON path.",
    )
    return parser.parse_args()


def skrf_output_base(touchstone: Path) -> str:
    return str(touchstone.with_suffix(""))


def main() -> None:
    args = parse_args()
    project = Path(args.project)
    touchstone = Path(args.touchstone)
    touchstone.parent.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "ok": False,
        "project": str(project),
        "design": args.design,
        "setup": args.setup,
        "sweep": args.sweep,
        "touchstone": str(touchstone),
        "attempts": [],
    }

    app = None
    try:
        app = Hfss3dLayout(
            project=str(project),
            design=args.design,
            version=args.version,
            non_graphical=True,
            new_desktop=True,
            close_on_exit=False,
        )
        summary["ports"] = app.port_list
        summary["setups"] = app.setup_names
        summary["sweeps"] = app.get_sweeps(args.setup)
        summary["traces"] = app.get_traces_for_plot(category="S")

        try:
            native = app.export_touchstone(
                setup=args.setup,
                sweep=args.sweep,
                output_file=str(touchstone),
                renormalization=True,
                impedance=50,
            )
            summary["attempts"].append({"method": "native_export_touchstone", "result": str(native)})
            if native and Path(native).exists():
                summary["ok"] = True
        except Exception as exc:
            summary["attempts"].append(
                {
                    "method": "native_export_touchstone",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

        if not summary["ok"]:
            try:
                networks = app.get_touchstone_data(setup=args.setup, sweep=args.sweep)
                if networks is False:
                    raise RuntimeError("get_touchstone_data returned False")
                summary["attempts"].append({"method": "get_touchstone_data", "count": len(networks)})
                if not networks:
                    raise RuntimeError("get_touchstone_data returned no networks")
                network = networks[0]
                network.write_touchstone(skrf_output_base(touchstone))
                generated = touchstone
                if not generated.exists():
                    candidates = sorted(touchstone.parent.glob(f"{touchstone.stem}.s*p"))
                    if candidates:
                        shutil.copyfile(candidates[0], touchstone)
                summary["ok"] = touchstone.exists()
                summary["fallback_port_names"] = getattr(network, "port_names", [])
                summary["fallback_frequency_points"] = len(getattr(network, "f", []))
            except Exception as exc:
                summary["attempts"].append(
                    {
                        "method": "get_touchstone_data_write_touchstone",
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
    except Exception as exc:
        summary["attempts"].append(
            {
                "method": "open_or_export",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        try:
            if app:
                app.release_desktop(close_projects=False, close_desktop=True)
        finally:
            summary_path = Path(args.summary)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
            print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
