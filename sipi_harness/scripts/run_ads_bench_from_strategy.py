from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from resample_touchstone_for_eye import preprocess_touchstone_for_eye

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "sipi_harness" / "scripts"


def load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if yaml is None:
        raise RuntimeError("PyYAML is required to read design_strategy.yaml.")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {path}")
    return data


def validation_benches(strategy: dict[str, Any]) -> dict[str, Any]:
    root = strategy.get("design_strategy", strategy)
    benches = root.get("validation_benches", {})
    return benches if isinstance(benches, dict) else {}


def metric_names(benches: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("generic_implementation_benches", "blocked_benches"):
        for item in benches.get(key, []) if isinstance(benches.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            for field in ("metric_name", "id", "bench_id", "implements_requirement", "requirement_family"):
                value = item.get(field)
                if value:
                    names.add(str(value).lower())
            synth = item.get("adapter_synthesis", {})
            if isinstance(synth, dict):
                for field in ("contract_id", "metric_name", "bench_type"):
                    value = synth.get(field)
                    if value:
                        names.add(str(value).lower())
    return names


def infer_package_class(strategy: dict[str, Any]) -> str:
    root = strategy.get("design_strategy", strategy)
    explicit_parts: list[str] = []
    for key in ("case", "request", "problem", "title"):
        value = strategy.get(key)
        if value:
            explicit_parts.append(str(value))
    if isinstance(root, dict):
        for key in ("request", "problem", "title"):
            value = root.get(key)
            if value:
                explicit_parts.append(str(value))
        request_parse = root.get("request_parse", {})
        if isinstance(request_parse, dict):
            explicit_parts.append(json.dumps(request_parse, ensure_ascii=False))
        package = root.get("package", {})
        if isinstance(package, dict):
            explicit_parts.append(json.dumps(package, ensure_ascii=False))
    text = " ".join(explicit_parts).lower()
    if "standard_package" in text or "standard package" in text or "standard-package" in text:
        return "standard_package"
    if "advanced_package" in text or "advanced package" in text:
        return "advanced_package"
    return "standard_package"


def infer_port_count(touchstone: Path) -> int:
    match = re.search(r"\.s(\d+)p$", touchstone.name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot infer port count from Touchstone extension: {touchstone}")
    return int(match.group(1))


def run_command(cmd: list[str], cwd: Path, timeout: int = 600) -> dict[str, Any]:
    cp = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "returncode": cp.returncode,
        "stdout_tail": cp.stdout[-4000:],
        "stderr_tail": cp.stderr[-4000:],
    }


def hpeesofsim_path(hpeesof_dir: Path) -> Path:
    return hpeesof_dir / "bin" / "hpeesofsim.exe"


def run_netlist_smoke(netlist: Path, run_dir: Path, hpeesof_dir: Path, touchstone: Path | None = None) -> dict[str, Any]:
    sim = hpeesofsim_path(hpeesof_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if touchstone is not None and touchstone.exists():
        shutil.copy2(touchstone, run_dir / touchstone.name)
    local_netlist = run_dir / netlist.name
    shutil.copy2(netlist, local_netlist)
    if not sim.exists():
        return {
            "netlist": str(netlist),
            "success": False,
            "returncode": None,
            "error": f"hpeesofsim.exe not found: {sim}",
        }
    log_path = run_dir / f"{netlist.stem}.hpeesofsim.log"
    env = os.environ.copy()
    env["HPEESOF_DIR"] = str(hpeesof_dir)
    env["COMPL_DIR"] = str(hpeesof_dir)
    env["PATH"] = os.pathsep.join(
        [
            str(hpeesof_dir / "bin"),
            str(hpeesof_dir / "tools" / "python"),
            str(hpeesof_dir / "adsptolemy" / "lib.win32_64"),
            env.get("PATH", ""),
        ]
    )
    with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
        cp = subprocess.run(
            [str(sim), f"./{local_netlist.name}"],
            cwd=str(run_dir),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            timeout=900,
        )
    combined_log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    lower_log = combined_log.lower()
    syntax_error = any(
        token in lower_log
        for token in (
            "syntax error",
            "syntax_error",
            "unexpected token",
            "parse error",
            "error detected by hpeesofsim",
        )
    )
    contour_missing = "failed to find open ber contour" in lower_log
    dataset_candidates = sorted(str(path) for path in run_dir.glob(f"{local_netlist.stem}*.ds"))
    return {
        "netlist": str(netlist),
        "local_netlist": str(local_netlist),
        "log": str(log_path),
        "success": cp.returncode == 0 and not syntax_error and not contour_missing,
        "returncode": cp.returncode,
        "syntax_error": syntax_error,
        "ber_contour_open": not contour_missing,
        "dataset_candidates": dataset_candidates,
        "blocker": (
            "ADS netlist syntax error. Repair the generated netlist before rerunning."
            if syntax_error
            else "BER contour at target BER was not open/found in ADS ChannelSim log."
            if contour_missing
            else None
        ),
        "stdout_tail": getattr(cp, "stdout", "")[-3000:] if getattr(cp, "stdout", None) else "",
        "stderr_tail": getattr(cp, "stderr", "")[-3000:] if getattr(cp, "stderr", None) else "",
        "log_tail": combined_log[-3000:],
    }


def write_final_ads_bench_report(summary: dict[str, Any], reports: Path) -> dict[str, str]:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        return {"report_error": f"matplotlib unavailable: {exc}"}

    reports.mkdir(parents=True, exist_ok=True)
    pdf_path = reports / "ads_bench_final_report.pdf"
    md_path = reports / "ads_bench_final_report.md"
    lines = [
        "# ADS Bench Final Report",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Touchstone: `{summary.get('touchstone')}`",
        f"- Port count: {summary.get('port_count')}",
        f"- Data rate: {summary.get('data_rate_gbps')} GT/s",
        f"- Detected metrics: {', '.join(summary.get('detected_metrics', []))}",
        "",
        "## Command Status",
        "",
    ]
    for name, result in summary.get("commands", {}).items():
        if not isinstance(result, dict):
            continue
        if "success" in result:
            status = f"success={result.get('success')} returncode={result.get('returncode')}"
        else:
            status = f"returncode={result.get('returncode')}"
        lines.append(f"- {name}: {status}")
        if result.get("log"):
            lines.append(f"  - log: `{result.get('log')}`")
    if summary.get("failed_commands") or summary.get("failed_smokes"):
        lines.extend(["", "## Blockers", ""])
        for name in summary.get("failed_commands", []):
            lines.append(f"- Failed command: `{name}`")
        for name in summary.get("failed_smokes", []):
            lines.append(f"- Failed smoke: `{name}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    vtf_json_path = Path(summary.get("outputs", {}).get("loaded_vtf_json", "__missing__"))
    vtf_payload: dict[str, Any] = {}
    if vtf_json_path.exists():
        try:
            vtf_payload = json.loads(vtf_json_path.read_text(encoding="utf-8"))
        except Exception:
            vtf_payload = {}

    with PdfPages(pdf_path) as pdf:
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        cover = [
            "ADS Bench Final Report",
            "",
            f"Status: {summary.get('status')}",
            f"Touchstone: {summary.get('touchstone')}",
            f"Port count: {summary.get('port_count')}",
            f"Data rate: {summary.get('data_rate_gbps')} GT/s",
            "",
            "Command status:",
        ]
        for name, result in summary.get("commands", {}).items():
            if isinstance(result, dict):
                if "success" in result:
                    cover.append(f"- {name}: success={result.get('success')} returncode={result.get('returncode')}")
                else:
                    cover.append(f"- {name}: returncode={result.get('returncode')}")
        if summary.get("failed_commands") or summary.get("failed_smokes"):
            cover.extend(["", "Blockers:"])
            for name in summary.get("failed_commands", []):
                cover.append(f"- failed command: {name}")
            for name in summary.get("failed_smokes", []):
                cover.append(f"- failed smoke: {name}")
        ax.text(0.04, 0.96, "\n".join(cover), va="top", ha="left", fontsize=10, family="monospace")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for key, title in [
            ("vtf_loss_png", "VTF Loss vs Frequency"),
            ("vtf_crosstalk_png", "VTF Crosstalk vs Frequency"),
            ("eye_density_contour_mask_png", "Eye Density, BER Contour, and Mask"),
        ]:
            image_value = summary.get("outputs", {}).get(key) or vtf_payload.get("plots", {}).get(key, "__missing__")
            image_path = Path(image_value)
            if image_path.exists():
                img = plt.imread(image_path)
                fig, ax = plt.subplots(figsize=(11, 8.5))
                ax.imshow(img)
                ax.axis("off")
                ax.set_title(title)
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
        eye = summary.get("commands", {}).get("channelsim_full_eye_netlist_smoke", {})
        if isinstance(eye, dict):
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis("off")
            text = [
                "Eye / BERContour Bench Status",
                "",
                f"Success: {eye.get('success')}",
                f"Return code: {eye.get('returncode')}",
                f"Netlist: {eye.get('netlist')}",
                f"Log: {eye.get('log')}",
                "",
                "Eye density, BER contour, and mask overlay are required for compliance.",
                "This report records the blocker when ChannelSim does not produce valid contour data.",
            ]
            ax.text(0.04, 0.96, "\n".join(text), va="top", ha="left", fontsize=10, family="monospace")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    return {"ads_bench_final_pdf": str(pdf_path), "ads_bench_final_markdown": str(md_path)}


def write_eye_dataset_report(workspace: Path, reports: Path, data_rate_gbps: float) -> dict[str, Any]:
    """Extract ADS ChannelSim eye density/BERContour and write report plots.

    ADS schematic runs write the usable dataset under workspace/data, while
    netlist-only smoke runs often write a smaller diagnostic .ds under
    netlist_runs. Prefer the schematic dataset because it is what engineers see
    in ADS DDS.
    """
    result: dict[str, Any] = {
        "status": "not_found",
        "density_present": False,
        "ber_contour_present": False,
        "ber_contour_valid": False,
    }
    candidate_map: dict[str, Path] = {}
    for pattern in (
        "channelsim_full_*lane_eye.ds",
        "channelsim_full_*lane_eye.ckt.ds",
        "channelsim_full_*lane_eye_check.ds",
        "channelsim_full_*lane_eye_check.ckt.ds",
        "channelsim_full_*lane_eye_template.ds",
        "channelsim_full_*lane_eye_template.ckt.ds",
    ):
        for path in workspace.rglob(pattern):
            candidate_map[str(path.resolve())] = path
    candidates = sorted(
        candidate_map.values(),
        key=lambda path: (
            0 if f"{os.sep}data{os.sep}" in str(path).lower() else 1,
            1 if f"{os.sep}netlist_runs{os.sep}" in str(path).lower() else 0,
            -path.stat().st_mtime,
        ),
    )
    result["dataset_candidates"] = [str(path) for path in candidates]
    if not candidates:
        result["reason"] = "No channelsim_full_*lane_eye*.ds dataset found."
        return result
    try:
        from keysight.ads import dataset
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        result["status"] = "blocked"
        result["reason"] = f"ADS dataset or matplotlib import failed: {exc}"
        return result

    open_errors: list[dict[str, str]] = []
    for ds_path in candidates:
        result["dataset"] = str(ds_path)
        try:
            ds = dataset.open(ds_path)
            density_name = next((name for name in ds.keys() if ".tdm.eye." in name.lower() and name.lower().endswith(".eye_l0")), None)
            contour_name = next((name for name in ds.keys() if ".tdm.eye.ber." in name.lower() and name.lower().endswith(".eye_l0")), None)
            measurements_name = next((name for name in ds.keys() if ".tdm.eyemeasurements." in name.lower()), None)
            if not density_name:
                open_errors.append({"dataset": str(ds_path), "error": "Eye density variable not found in ADS dataset."})
                continue
            density_df = ds.get(density_name).to_dataframe().reset_index()
            result["density_variable"] = density_name
            result["density_rows"] = int(len(density_df))
            result["density_present"] = "Density" in density_df.columns and len(density_df) > 10

            contour_df = None
            if contour_name:
                contour_df = ds.get(contour_name).to_dataframe().reset_index()
                result["ber_contour_variable"] = contour_name
                result["ber_contour_rows"] = int(len(contour_df))
                result["ber_contour_present"] = "BERContour" in contour_df.columns and len(contour_df) > 10
                if result["ber_contour_present"]:
                    values = [float(value) for value in contour_df["BERContour"].values]
                    result["ber_contour_valid"] = max(values) > min(values)

            if measurements_name:
                measurements = ds.get(measurements_name).to_dataframe()
                result["measurements_variable"] = measurements_name
                for col in measurements.columns:
                    try:
                        result[str(col)] = float(measurements[col].iloc[0])
                    except Exception:
                        pass
            break
        except Exception as exc:
            open_errors.append({"dataset": str(ds_path), "error": str(exc)})
            continue
    else:
        result["status"] = "blocked"
        result["open_errors"] = open_errors
        result["reason"] = "No readable ADS eye dataset was found."
        return result

    try:
        reports.mkdir(parents=True, exist_ok=True)
        png_path = reports / "ads_eye_density_contour_mask.png"
        pdf_path = reports / "ads_eye_density_contour_mask_report.pdf"

        time_ps = density_df["time"].astype(float) * 1e12
        voltage = density_df["Density"].astype(float)
        color = density_df["index"].astype(float) if "index" in density_df.columns else None
        fig, ax = plt.subplots(figsize=(10.5, 5.2))
        scatter = ax.scatter(time_ps, voltage, c=color, s=2.0, cmap="turbo", alpha=0.45, linewidths=0)
        cbar = fig.colorbar(scatter, ax=ax, pad=0.01)
        cbar.set_label("ADS density index")
        if contour_df is not None and result["ber_contour_present"]:
            contour_time_ps = contour_df["time"].astype(float) * 1e12
            contour_voltage = contour_df["BERContour"].astype(float)
            ax.plot(contour_time_ps, contour_voltage, color="red", linewidth=1.3, label="BERContour")
        ui_ps = 1e3 / data_rate_gbps
        mask_width_ps = 0.75 * ui_ps
        mask_height_v = 0.040
        if contour_df is not None and result["ber_contour_present"]:
            center_t = float((contour_time_ps.min() + contour_time_ps.max()) / 2.0)
        else:
            center_t = float((time_ps.min() + time_ps.max()) / 2.0)
        level0 = result.get("Level0")
        level1 = result.get("Level1")
        center_v = (float(level0) + float(level1)) / 2.0 if level0 is not None and level1 is not None else float(voltage.median())
        rect_x = center_t - mask_width_ps / 2.0
        rect_y = center_v - mask_height_v / 2.0
        ax.add_patch(
            plt.Rectangle(
                (rect_x, rect_y),
                mask_width_ps,
                mask_height_v,
                fill=False,
                edgecolor="black",
                linestyle="--",
                linewidth=1.4,
                label="Rectangular mask",
            )
        )
        result["mask_center_time_ps"] = center_t
        result["mask_center_voltage_v"] = center_v
        result["mask_width_ps"] = mask_width_ps
        result["mask_height_v"] = mask_height_v
        ax.set_title("ADS ChannelSim Eye Density, BER Contour, and Rectangular Mask")
        ax.set_xlabel("time (ps)")
        ax.set_ylabel("voltage (V)")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
        fig.savefig(png_path, dpi=180, bbox_inches="tight")
        with PdfPages(pdf_path) as pdf:
            pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
        result["status"] = "ok" if result["density_present"] and result["ber_contour_valid"] else "blocked"
        result["eye_density_contour_mask_png"] = str(png_path)
        result["eye_density_contour_mask_pdf"] = str(pdf_path)
        return result
    except Exception as exc:
        result["status"] = "blocked"
        result["reason"] = str(exc)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ADS/bench verification from source-derived strategy contracts instead of stopping at missing static adapters."
    )
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--port-intents", type=Path, required=True)
    parser.add_argument("--data-rate-gbps", type=float, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--hpeesof-dir", type=Path, default=Path(os.environ.get("HPEESOF_DIR", r"C:\Program Files\Keysight\ADS2026_Update2")))
    parser.add_argument("--skip-netlist-smoke", action="store_true")
    parser.add_argument(
        "--eye-max-step-ghz",
        type=float,
        default=None,
        help="Maximum allowed Touchstone frequency step before ADS ChannelSim eye interpolation. Default is min(0.05 GHz, Nyquist/40).",
    )
    parser.add_argument(
        "--eye-min-points",
        type=int,
        default=101,
        help="Minimum Touchstone point count before ADS ChannelSim eye interpolation is triggered.",
    )
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    args.workspace.mkdir(parents=True, exist_ok=True)
    reports = args.workspace / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    data = args.workspace / "data"
    data.mkdir(exist_ok=True)
    local_touchstone = data / args.touchstone.name
    if args.touchstone.resolve() != local_touchstone.resolve():
        shutil.copy2(args.touchstone, local_touchstone)

    strategy = load_yaml_or_json(args.strategy)
    benches = validation_benches(strategy)
    metrics = metric_names(benches)
    package_class = infer_package_class(strategy)
    port_count = infer_port_count(local_touchstone)

    summary: dict[str, Any] = {
        "schema_version": "ads_bench_from_strategy_v1",
        "status": "started",
        "strategy": str(args.strategy),
        "workspace": str(args.workspace),
        "touchstone": str(local_touchstone),
        "port_intents": str(args.port_intents),
        "port_count": port_count,
        "data_rate_gbps": args.data_rate_gbps,
        "package_class": package_class,
        "detected_metrics": sorted(metrics),
        "adapter_policy": "Do not stop at missing static adapters. Generate and run strategy-derived ADS/bench artifacts when required inputs exist.",
        "commands": {},
        "outputs": {},
        "blockers": [],
    }

    adapter_plan = reports / "bench_adapter_plan.json"
    plan_cmd = [
        sys.executable,
        str(SCRIPTS / "create_bench_adapter_plan.py"),
        "--strategy",
        str(args.strategy),
        "--out-dir",
        str(args.workspace / "adapter_plan"),
    ]
    summary["commands"]["adapter_plan"] = run_command(plan_cmd, ROOT / "sipi_harness", timeout=120)
    summary["outputs"]["adapter_plan"] = str(args.workspace / "adapter_plan" / "bench_adapter_plan.json")

    joined_metrics = " ".join(sorted(metrics))
    eye_required = bool(metrics & {"eye_mask", "ber_contour", "bathtub", "jitter"}) or any(
        token in joined_metrics for token in ("eye", "ber", "contour", "bathtub", "jitter", "mask")
    )

    eye_touchstone = local_touchstone
    eye_preprocess_summary: dict[str, Any] | None = None
    if eye_required:
        eye_touchstone, eye_preprocess_summary = preprocess_touchstone_for_eye(
            local_touchstone,
            data,
            args.data_rate_gbps,
            max_step_ghz=args.eye_max_step_ghz,
            min_points=args.eye_min_points,
        )
        summary["outputs"]["eye_touchstone"] = str(eye_touchstone)
        summary["outputs"]["eye_touchstone_preprocess"] = eye_preprocess_summary
        eye_summary_path = reports / "eye_touchstone_preprocess_summary.json"
        eye_summary_path.write_text(json.dumps(eye_preprocess_summary, indent=2), encoding="utf-8")
        summary["outputs"]["eye_touchstone_preprocess_summary"] = str(eye_summary_path)

    bench_workspace = args.workspace / "ads_bench_wrk"
    existing_schematic_eye_ds = list((bench_workspace / "data").glob("channelsim_full_*lane_eye*.ds"))
    bench_cmd = [
        sys.executable,
        str(SCRIPTS / "create_ads_bench_templates.py"),
        "--workspace",
        str(bench_workspace),
        "--touchstone-name",
        eye_touchstone.name if eye_required else local_touchstone.name,
        "--port-count",
        str(port_count),
    ]
    if eye_preprocess_summary and eye_preprocess_summary.get("resampled"):
        bench_cmd.append("--overwrite")
    elif not existing_schematic_eye_ds:
        bench_cmd.append("--overwrite")
    summary["commands"]["ads_bench_workspace"] = run_command(bench_cmd, ROOT / "sipi_harness", timeout=240)
    summary["outputs"]["ads_bench_workspace"] = str(bench_workspace)
    summary["outputs"]["ads_bench_summary"] = str(bench_workspace / "reports" / "ads_bench_summary.json")
    summary["outputs"]["preserved_existing_schematic_eye_dataset"] = [str(path) for path in existing_schematic_eye_ds]
    bench_data = bench_workspace / "data"
    bench_data.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_touchstone, bench_data / local_touchstone.name)
    if eye_required and eye_touchstone.resolve() != local_touchstone.resolve():
        shutil.copy2(eye_touchstone, bench_data / eye_touchstone.name)

    vtf_required = bool(metrics & {"voltage_transfer_function", "loading_model", "crosstalk"}) or any(
        token in joined_metrics for token in ("vtf", "voltage_transfer", "xt", "xtlk", "crosstalk")
    )
    if vtf_required:
        vtf_cmd = [
            sys.executable,
            str(SCRIPTS / "run_ads_full_vtf_verification.py"),
            "--workspace",
            str(args.workspace / "loaded_vtf_wrk"),
            "--touchstone",
            str(local_touchstone),
            "--port-intents",
            str(args.port_intents),
            "--data-rate-gbps",
            str(args.data_rate_gbps),
            "--package-class",
            package_class,
            "--hpeesof-dir",
            str(args.hpeesof_dir),
            "--run-ads-smoke",
        ]
        summary["commands"]["loaded_vtf"] = run_command(vtf_cmd, ROOT / "sipi_harness", timeout=900)
        summary["outputs"]["loaded_vtf_json"] = str(args.workspace / "loaded_vtf_wrk" / "reports" / "ads_full_vtf_verification.json")
        summary["outputs"]["loaded_vtf_markdown"] = str(args.workspace / "loaded_vtf_wrk" / "reports" / "ads_full_vtf_verification.md")
    else:
        summary["outputs"]["loaded_vtf"] = "not_required_by_strategy_metrics"

    if eye_required:
        lane_count = port_count // 2
        per_lane_workspace = bench_workspace / "per_lane_eye_wrk"
        per_lane_summary = reports / "ads_per_lane_eye_report.json"
        if not args.skip_netlist_smoke:
            per_lane_cmd = [
                sys.executable,
                str(SCRIPTS / "run_ads_per_lane_eye_report.py"),
                "--workspace",
                str(per_lane_workspace),
                "--touchstone",
                str(eye_touchstone),
                "--lane-count",
                str(lane_count),
                "--data-rate-gbps",
                str(args.data_rate_gbps),
                "--hpeesof-dir",
                str(args.hpeesof_dir),
                "--summary",
                str(per_lane_summary),
            ]
            summary["commands"]["channelsim_per_lane_eye_report"] = run_command(
                per_lane_cmd, ROOT / "sipi_harness", timeout=max(900, 240 * lane_count)
            )
            if per_lane_summary.exists():
                per_lane_report = json.loads(per_lane_summary.read_text(encoding="utf-8"))
                summary["outputs"]["eye_dataset_report"] = per_lane_report
                summary["outputs"]["per_lane_eye_report_json"] = str(per_lane_summary)
                for source_key, dest_key in [
                    ("eye_density_contour_mask_png", "eye_density_contour_mask_png"),
                    ("eye_density_contour_mask_pdf", "eye_density_contour_mask_pdf"),
                    ("eye_density_contour_mask_8lane_png", "eye_density_contour_mask_8lane_png"),
                    ("eye_density_contour_mask_8lane_pdf", "eye_density_contour_mask_8lane_pdf"),
                ]:
                    value = per_lane_report.get(source_key)
                    if value:
                        src = Path(value)
                        dst = reports / src.name
                        if src.exists() and src.resolve() != dst.resolve():
                            shutil.copy2(src, dst)
                            summary["outputs"][dest_key] = str(dst)
                        else:
                            summary["outputs"][dest_key] = str(src)
                if (
                    per_lane_report.get("lane_count_reported") == lane_count
                    and per_lane_report.get("density_present")
                    and per_lane_report.get("ber_contour_valid")
                ):
                    summary["commands"]["channelsim_per_lane_eye_report"]["success"] = True
                    summary["commands"]["channelsim_per_lane_eye_report"]["blocker"] = None
                else:
                    summary["commands"]["channelsim_per_lane_eye_report"]["success"] = False
                    summary["commands"]["channelsim_per_lane_eye_report"]["blocker"] = (
                        "Per-lane ChannelSim did not produce valid density and BERContour for every lane."
                    )
            else:
                summary["blockers"].append(
                    {
                        "metric": "eye_mask/ber_contour",
                        "reason": "Per-lane ADS ChannelSim summary was not generated.",
                        "expected_summary": str(per_lane_summary),
                    }
                )
        else:
            summary["blockers"].append(
                {
                    "metric": "eye_mask/ber_contour",
                    "reason": "Per-lane ADS ChannelSim eye report was skipped.",
                    "expected_lane_count": lane_count,
                }
            )

    failed_commands = [
        name
        for name, result in summary["commands"].items()
        if isinstance(result, dict) and result.get("returncode") not in {0, None}
    ]
    failed_smokes = [
        name
        for name, result in summary["commands"].items()
        if isinstance(result, dict) and result.get("success") is False
    ]
    if failed_commands or failed_smokes or summary["blockers"]:
        summary["status"] = "bench_attempted_with_blockers"
        summary["failed_commands"] = failed_commands
        summary["failed_smokes"] = failed_smokes
    else:
        summary["status"] = "bench_artifacts_generated_and_ads_smoke_passed"

    summary["outputs"].update(write_final_ads_bench_report(summary, reports))

    summary_path = args.summary or reports / "ads_bench_from_strategy_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary": str(summary_path), "status": summary["status"]}, indent=2))
    return 0 if summary["status"] != "started" else 1


if __name__ == "__main__":
    raise SystemExit(main())
