from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


FIXED_SNP_PORTS = {2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16}


def hpeesofsim_path(hpeesof_dir: Path) -> Path:
    return hpeesof_dir / "bin" / "hpeesofsim.exe"


def write_lane_netlist(path: Path, touchstone_name: str, lane_count: int, victim_lane: int, data_rate_gbps: float) -> None:
    port_count = lane_count * 2
    fixed_symbol = f"S{port_count}P" if port_count in FIXED_SNP_PORTS else "SnP"
    nodes: list[str] = []
    for lane in range(lane_count):
        nodes.extend([f"tx{lane}", f"rx{lane}"])
    lines = [
        f"; Per-lane ChannelSim eye bench, victim lane {victim_lane}.",
        'ChannelSim:ChannelSim1 Type="Statistical" ToleranceMode=1 EnforcePassivity=yes MaxImpulseLength=1000 NumberTimePtPerUI=32 StatusLevel=2 AntiAliasingWindow=1 ImpLFEOn=yes ImpCache=yes',
        '#load "python","TDM_Eye"',
        (
            f'ComponentWithNodes:EYE_L{victim_lane} rx{victim_lane} Type="ModelExtractor" Module="Eye" '
            'Save_LevelMean=no Save_HeightAtBER=yes Save_Level1=yes Save_JitterRMS=no Save_Density=yes '
            'Save_RiseTime=no Save_Height=yes Save_Level0=yes Save_Width=yes Save_CheckMaskViolation=no '
            'Save_SNR=no Save_Amplitude=no Save_HeightDB=no Save_FallTime=no Save_WidthAtBER=yes '
            'Save_JitterPP=no Save_Bathtub=no Save_Waveform=no Save_Contour=yes Save_CrossingLevel=no '
            'Save_ClockSignal=no Save_DDR4MaskMargin=no LowerBoundary=40 UpperThreshold=80 DataRate=1.0 Gbps '
            'LowerThreshold=20 UpperBoundary=60 TimePoints=400 AmplitudeResolution=0.001 V BERWidthHeight=1e-27 '
            f'TimingBathTub=0.0 V EyeMask="EYE_L{victim_lane}" UseEyeMask=0 BERContour=list(1e-27) '
            'ExtrapolateBER=yes VoltageBathTub=0.5 DisableTransientOutput=yes DDR4MaskWidthUI=0.0 '
            'DDR4MaskHeight=0.0 V Save_BathtubQPlot=no Save_VSRPAM4=no SetDDR4MaskCenter=0 '
            'DDR4MaskCenter=0.0 V SetDDR4MaskGroup=0 DDR4MaskGroup=1 LoadScopeSetupFile=no '
            'SplitFlexDCAwaveform=no Save_FlexDCAmeasurements=no'
        ),
        f'TX:TX_VICTIM_L{victim_lane} drv{victim_lane} BitRate={data_rate_gbps:g} Gbps Model="ADSTx" Vhigh=1.1 V Vlow=0 V RiseFallTime=100 psec Mode=0 RegisterLength=8 Encoder=0 TapInterval=1.0 EQMode=0',
    ]
    for lane in range(lane_count):
        if lane == victim_lane:
            continue
        lines.append(
            f'XTLK:XTLK2_L{lane} drv{lane} Model="ADSXtlk" NewModel=yes SameSourceSettingAsTx=yes PhaseToTxMode=0 PhaseToTx=0.0 Vhigh=1.0 V Vlow=0.0 V RiseFallTime=100 psec'
        )
    lines.extend(
        [
            f'#uselib "ckt" , "{fixed_symbol}"',
            f'{fixed_symbol}:SNP_FULL {" ".join(nodes)} 0 File="{touchstone_name}" Type="touchstone" InterpMode="linear" InterpDom="" ExtrapMode="constant" Temp=27.0 CheckPassivity=0',
        ]
    )
    for lane in range(lane_count):
        lines.append(f"R:R_TX_SRC_L{lane} drv{lane} tx{lane} R=30 Ohm Noise=yes")
        lines.append(f"C:C_TX_L{lane} tx{lane} 0 C=0.2 pF")
        lines.append(f"R:R_RX_L{lane} rx{lane} 0 R=50 Ohm Noise=yes")
        lines.append(f"C:C_RX_L{lane} rx{lane} 0 C=0.2 pF")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_lane(netlist: Path, run_dir: Path, hpeesof_dir: Path, touchstone: Path) -> dict[str, Any]:
    sim = hpeesofsim_path(hpeesof_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(touchstone, run_dir / touchstone.name)
    local_netlist = run_dir / netlist.name
    shutil.copy2(netlist, local_netlist)
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
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    lower = log.lower()
    syntax_error = any(token in lower for token in ("syntax error", "parse error", "error detected by hpeesofsim"))
    contour_missing = "failed to find open ber contour" in lower
    datasets = sorted(run_dir.glob(f"{local_netlist.stem}*.ds"))
    return {
        "netlist": str(netlist),
        "run_dir": str(run_dir),
        "log": str(log_path),
        "returncode": cp.returncode,
        "success": cp.returncode == 0 and not syntax_error and bool(datasets),
        "syntax_error": syntax_error,
        "ber_contour_open": not contour_missing,
        "datasets": [str(path) for path in datasets],
        "log_tail": log[-3000:],
    }


def extract_lane(ds_path: Path, lane: int) -> dict[str, Any]:
    from keysight.ads import dataset

    ds = dataset.open(ds_path)
    density_name = f"ChannelSim1.TDM.Eye.EYE_L{lane}"
    contour_name = f"ChannelSim1.TDM.Eye.BER.EYE_L{lane}"
    measurements_name = f"ChannelSim1.TDM.EyeMeasurements.EYE_L{lane}"
    density_df = ds.get(density_name).to_dataframe().reset_index()
    contour_df = ds.get(contour_name).to_dataframe().reset_index() if contour_name in ds.keys() else None
    measurements = ds.get(measurements_name).to_dataframe() if measurements_name in ds.keys() else None
    report: dict[str, Any] = {
        "lane": lane,
        "dataset": str(ds_path),
        "density_variable": density_name,
        "density_rows": int(len(density_df)),
        "density_present": "Density" in density_df.columns and len(density_df) > 10,
        "ber_contour_variable": contour_name if contour_df is not None else None,
        "ber_contour_rows": int(len(contour_df)) if contour_df is not None else 0,
        "ber_contour_present": contour_df is not None and "BERContour" in contour_df.columns and len(contour_df) > 10,
    }
    if report["ber_contour_present"] and contour_df is not None:
        values = [float(value) for value in contour_df["BERContour"].values]
        report["ber_contour_valid"] = max(values) > min(values)
    else:
        report["ber_contour_valid"] = False
    if measurements is not None:
        for col in measurements.columns:
            try:
                report[str(col)] = float(measurements[col].iloc[0])
            except Exception:
                pass
    return {"report": report, "density": density_df, "contour": contour_df}


def plot_lanes(lane_data: list[dict[str, Any]], reports: Path, data_rate_gbps: float) -> dict[str, str]:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    reports.mkdir(parents=True, exist_ok=True)
    png_path = reports / "ads_eye_density_contour_mask_8lane.png"
    pdf_path = reports / "ads_eye_density_contour_mask_8lane_report.pdf"
    legacy_png = reports / "ads_eye_density_contour_mask.png"
    legacy_pdf = reports / "ads_eye_density_contour_mask_report.pdf"
    cols = 2
    rows = (len(lane_data) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(12.0, max(4.0, rows * 3.1)), squeeze=False)
    scatter = None
    ui_ps = 1e3 / data_rate_gbps
    mask_width_ps = 0.75 * ui_ps
    mask_height_v = 0.040
    for item, ax in zip(lane_data, axes.flatten()):
        lane = int(item["report"]["lane"])
        density = item["density"]
        contour = item.get("contour")
        time_ps = density["time"].astype(float) * 1e12
        voltage = density["Density"].astype(float)
        color = density["index"].astype(float) if "index" in density.columns else None
        scatter = ax.scatter(time_ps, voltage, c=color, s=1.2, cmap="turbo", alpha=0.42, linewidths=0)
        if contour is not None and "BERContour" in contour.columns and len(contour) > 0:
            contour_time_ps = contour["time"].astype(float) * 1e12
            contour_voltage = contour["BERContour"].astype(float)
            ax.plot(contour_time_ps, contour_voltage, color="red", linewidth=1.0, label="BERContour")
            center_t = float((contour_time_ps.min() + contour_time_ps.max()) / 2.0)
        else:
            center_t = float((time_ps.min() + time_ps.max()) / 2.0)
        level0 = item["report"].get("Level0")
        level1 = item["report"].get("Level1")
        center_v = (
            (float(level0) + float(level1)) / 2.0
            if level0 is not None and level1 is not None
            else float(voltage.median())
        )
        item["report"]["mask_center_time_ps"] = center_t
        item["report"]["mask_center_voltage_v"] = center_v
        ax.add_patch(
            plt.Rectangle(
                (center_t - mask_width_ps / 2.0, center_v - mask_height_v / 2.0),
                mask_width_ps,
                mask_height_v,
                fill=False,
                edgecolor="black",
                linestyle="--",
                linewidth=1.0,
                label="Rectangular mask",
            )
        )
        ax.set_title(f"Lane {lane} Eye")
        ax.set_xlabel("time (ps)")
        ax.set_ylabel("voltage (V)")
        ax.grid(True, alpha=0.25)
    for ax in axes.flatten()[len(lane_data):]:
        ax.axis("off")
    if scatter is not None:
        cbar = fig.colorbar(scatter, ax=axes.ravel().tolist(), pad=0.01)
        cbar.set_label("ADS density index")
    fig.suptitle("ADS ChannelSim Eye Density, BER Contour, and Rectangular Mask by Lane")
    fig.savefig(png_path, dpi=180, bbox_inches="tight")
    with PdfPages(pdf_path) as pdf:
        pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    shutil.copy2(png_path, legacy_png)
    shutil.copy2(pdf_path, legacy_pdf)
    return {
        "eye_density_contour_mask_8lane_png": str(png_path),
        "eye_density_contour_mask_8lane_pdf": str(pdf_path),
        "eye_density_contour_mask_png": str(legacy_png),
        "eye_density_contour_mask_pdf": str(legacy_pdf),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one ADS ChannelSim eye bench per victim lane and create an all-lane eye report.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--lane-count", type=int, required=True)
    parser.add_argument("--data-rate-gbps", type=float, required=True)
    parser.add_argument("--hpeesof-dir", type=Path, default=Path(os.environ.get("HPEESOF_DIR", r"C:\Program Files\Keysight\ADS2026_Update2")))
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    args.workspace.mkdir(parents=True, exist_ok=True)
    netlists = args.workspace / "netlists"
    run_root = args.workspace / "lane_runs"
    reports = args.workspace / "reports"
    netlists.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    lane_data: list[dict[str, Any]] = []
    for lane in range(args.lane_count):
        netlist = netlists / f"channelsim_eye_lane{lane}.ckt"
        write_lane_netlist(netlist, args.touchstone.name, args.lane_count, lane, args.data_rate_gbps)
        run = run_lane(netlist, run_root / f"lane_{lane}", args.hpeesof_dir, args.touchstone)
        run["lane"] = lane
        runs.append(run)
        if run["datasets"]:
            try:
                lane_data.append(extract_lane(Path(run["datasets"][0]), lane))
            except Exception as exc:
                run["extract_error"] = str(exc)

    outputs = plot_lanes(lane_data, reports, args.data_rate_gbps) if lane_data else {}
    lane_reports = [item["report"] for item in lane_data]
    payload = {
        "schema_version": "ads_per_lane_eye_report_v1",
        "status": "ok" if len(lane_data) == args.lane_count else "partial_or_blocked",
        "workspace": str(args.workspace),
        "touchstone": str(args.touchstone),
        "lane_count_requested": args.lane_count,
        "lane_count_reported": len(lane_data),
        "density_present": len(lane_data) == args.lane_count and all(item.get("density_present") for item in lane_reports),
        "ber_contour_present": len(lane_data) == args.lane_count and all(item.get("ber_contour_present") for item in lane_reports),
        "ber_contour_valid": len(lane_data) == args.lane_count and all(item.get("ber_contour_valid") for item in lane_reports),
        "runs": runs,
        "lanes": lane_reports,
        **outputs,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"summary": str(args.summary), "status": payload["status"], "lane_count_reported": len(lane_data)}, indent=2))
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
