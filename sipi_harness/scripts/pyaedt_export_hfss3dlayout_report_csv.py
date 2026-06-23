from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from ansys.aedt.core import Hfss3dLayout

    PYAEDT_API = "ansys.aedt.core"
except ModuleNotFoundError:
    from pyaedt import Hfss3dLayout

    PYAEDT_API = "pyaedt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export HFSS 3D Layout S-parameter report CSV through PyAEDT post API.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--design", required=True)
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--solution", required=True)
    parser.add_argument("--ports", type=int, default=2)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--plot-name", default="SParam_Export")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--non-graphical", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.project).resolve()
    out_dir = Path(args.out_dir).resolve()
    summary_path = Path(args.summary).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    expressions = [f"S(Port{i},Port{j})" for i in range(1, args.ports + 1) for j in range(1, args.ports + 1)]
    summary: dict[str, object] = {
        "ok": False,
        "project": str(project),
        "design": args.design,
        "solution": args.solution,
        "expressions": expressions,
        "pyaedt_api": PYAEDT_API,
        "attempts": [],
    }
    app = None
    try:
        if PYAEDT_API == "ansys.aedt.core":
            app = Hfss3dLayout(
                project=str(project),
                design=args.design,
                version=args.version,
                non_graphical=args.non_graphical,
                new_desktop=True,
                close_on_exit=False,
            )
        else:
            app = Hfss3dLayout(
                projectname=str(project),
                designname=args.design,
                specified_version=args.version,
                non_graphical=args.non_graphical,
                new_desktop_session=True,
                close_on_exit=False,
            )
        summary["ports"] = list(app.port_list)
        summary["setups"] = list(app.setup_names)
        summary["available_report_solutions"] = list(app.post.available_report_solutions("Standard"))
        summary["available_report_quantities"] = list(
            app.post.available_report_quantities(
                report_category="Standard",
                display_type="Rectangular Plot",
                solution=args.solution,
            )
        )
        report = app.post.create_report(
            expressions=expressions,
            setup_sweep_name=args.solution,
            domain="Sweep",
            variations={"Freq": ["All"]},
            primary_sweep_variable="Freq",
            report_category="Standard",
            plot_type="Rectangular Plot",
            plot_name=args.plot_name,
            show=False,
        )
        summary["attempts"].append({"method": "post.create_report", "result": str(bool(report)), "report_type": type(report).__name__})
        csv_path = app.post.export_report_to_csv(str(out_dir), args.plot_name)
        summary["attempts"].append({"method": "post.export_report_to_csv", "result": str(csv_path)})
        if csv_path and Path(csv_path).exists():
            summary["csv"] = str(Path(csv_path).resolve())
            summary["csv_size"] = Path(csv_path).stat().st_size
            summary["ok"] = summary["csv_size"] > 0
        else:
            candidates = sorted(out_dir.glob(f"{args.plot_name}*.csv"))
            summary["csv_candidates"] = [str(path) for path in candidates]
            if candidates:
                summary["csv"] = str(candidates[0].resolve())
                summary["csv_size"] = candidates[0].stat().st_size
                summary["ok"] = summary["csv_size"] > 0
    except Exception as exc:
        summary["error"] = str(exc)
    finally:
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        if app:
            try:
                app.release_desktop(close_projects=True, close_desktop=False)
            except Exception as exc:
                summary["release_warning"] = str(exc)
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
