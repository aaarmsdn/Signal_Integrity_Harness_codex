from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
from pathlib import Path


def db20(value: complex) -> float:
    return 20.0 * math.log10(max(abs(value), 1e-300))


def db10_power(values: list[complex]) -> float:
    return 10.0 * math.log10(max(sum(abs(value) ** 2 for value in values), 1e-300))


def parse_touchstone(path: Path) -> tuple[list[float], list[list[list[complex]]], float, str]:
    match = re.search(r"\.s(\d+)p$", path.name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot infer Touchstone port count from {path}")
    ports = int(match.group(1))
    scale = 1.0
    fmt = "MA"
    zref = 50.0
    option = ""
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
            if "R" in parts:
                idx = parts.index("R")
                if idx + 1 < len(parts):
                    zref = float(parts[idx + 1])
            continue
        nums.extend(float(tok) for tok in line.split())
        while len(nums) >= values_per:
            block = nums[:values_per]
            nums = nums[values_per:]
            freqs.append(block[0] * scale)
            values = block[1:]
            mat = [[0j for _ in range(ports)] for _ in range(ports)]
            idx = 0
            for col in range(ports):
                for row in range(ports):
                    a, b = values[idx], values[idx + 1]
                    idx += 2
                    if fmt == "RI":
                        mat[row][col] = complex(a, b)
                    elif fmt == "DB":
                        mag = 10 ** (a / 20.0)
                        mat[row][col] = mag * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
                    else:
                        mat[row][col] = a * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
            mats.append(mat)
    if option.upper().startswith("# HZ") and freqs and max(freqs) < 1e-3:
        freqs = [f * 1e9 for f in freqs]
        option += "  ! frequency_unit_corrected_from_mislabeled_hz_to_ghz"
    return freqs, mats, zref, option


def identity(n: int) -> list[list[complex]]:
    return [[1 + 0j if i == j else 0j for j in range(n)] for i in range(n)]


def mat_add(a: list[list[complex]], b: list[list[complex]], sign: int = 1) -> list[list[complex]]:
    return [[a[i][j] + sign * b[i][j] for j in range(len(a))] for i in range(len(a))]


def mat_mul(a: list[list[complex]], b: list[list[complex]]) -> list[list[complex]]:
    n = len(a)
    return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]


def mat_inv(a: list[list[complex]]) -> list[list[complex]]:
    n = len(a)
    aug = [row[:] + ident[:] for row, ident in zip(a, identity(n))]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-30:
            raise ValueError("Singular matrix while converting S to Y")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        piv = aug[col][col]
        aug[col] = [v / piv for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [v - factor * pv for v, pv in zip(aug[row], aug[col])]
    return [row[n:] for row in aug]


def solve_linear(a: list[list[complex]], b: list[complex]) -> list[complex]:
    n = len(a)
    aug = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-30:
            raise ValueError("Singular nodal matrix")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        piv = aug[col][col]
        aug[col] = [v / piv for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [v - factor * pv for v, pv in zip(aug[row], aug[col])]
    return [row[-1] for row in aug]


def s_to_y(s: list[list[complex]], zref: float) -> list[list[complex]]:
    n = len(s)
    ident = identity(n)
    return [[v / zref for v in row] for row in mat_mul(mat_add(ident, s, sign=-1), mat_inv(mat_add(ident, s)))]


def interp_matrix(freqs: list[float], mats: list[list[list[complex]]], target_ghz: float) -> tuple[float, list[list[complex]], str]:
    if target_ghz <= freqs[0]:
        return freqs[0], mats[0], "clamped_low"
    if target_ghz >= freqs[-1]:
        return freqs[-1], mats[-1], "clamped_high"
    for idx in range(len(freqs) - 1):
        f0, f1 = freqs[idx], freqs[idx + 1]
        if f0 <= target_ghz <= f1:
            if abs(target_ghz - f0) < 1e-12:
                return f0, mats[idx], "exact"
            if abs(target_ghz - f1) < 1e-12:
                return f1, mats[idx + 1], "exact"
            t = (target_ghz - f0) / (f1 - f0)
            n = len(mats[idx])
            mat = [[mats[idx][r][c] * (1 - t) + mats[idx + 1][r][c] * t for c in range(n)] for r in range(n)]
            return target_ghz, mat, "linear_interpolated"
    return freqs[-1], mats[-1], "fallback"


def ucie_loading(data_rate_gbps: float) -> dict[str, float]:
    if data_rate_gbps <= 8.0:
        return {
            "ctx_pf": 0.3,
            "crx_term_pf": 0.3,
            "crx_no_term_pf": 0.2,
            "rxterm_loss_limit_db": -7.5,
            "no_rxterm_loss_limit_db": -1.25,
            "no_rxterm_xt_a": 7.0,
            "no_rxterm_xt_b": -12.5,
            "no_rxterm_xt_floor_db": -15.0,
        }
    if data_rate_gbps <= 16.0:
        return {
            "ctx_pf": 0.2,
            "crx_term_pf": 0.2,
            "crx_no_term_pf": 0.2,
            "rxterm_loss_limit_db": -6.5,
            "no_rxterm_loss_limit_db": -1.15,
            "no_rxterm_xt_a": 4.0,
            "no_rxterm_xt_b": -13.5,
            "no_rxterm_xt_floor_db": -17.0,
        }
    return {
        "ctx_pf": 0.125,
        "crx_term_pf": 0.125,
        "crx_no_term_pf": 0.125,
        "rxterm_loss_limit_db": -7.5,
        "no_rxterm_loss_limit_db": -1.15,
        "no_rxterm_xt_a": 4.0,
        "no_rxterm_xt_b": -13.5,
        "no_rxterm_xt_floor_db": -17.0,
    }


def solve_loaded_channel(
    y_channel: list[list[complex]],
    freq_ghz: float,
    active_lane: int,
    rxterm: bool,
    lane_count: int,
    loading: dict[str, float],
) -> list[complex]:
    n = 2 * lane_count
    a = [row[:] for row in y_channel]
    b = [0j for _ in range(n)]
    omega = 2 * math.pi * freq_ghz * 1e9
    rtx = 30.0
    rrx = 50.0
    gtx = 1.0 / rtx
    grx = 1.0 / rrx
    y_ctx = 1j * omega * loading["ctx_pf"] * 1e-12
    crx_pf = loading["crx_term_pf"] if rxterm else loading["crx_no_term_pf"]
    y_crx = 1j * omega * crx_pf * 1e-12
    for lane in range(lane_count):
        tx = 2 * lane
        rx = tx + 1
        a[tx][tx] += y_ctx
        a[rx][rx] += y_crx
        if lane == active_lane:
            a[tx][tx] += gtx
            b[tx] += gtx * 1.0
        else:
            a[tx][tx] += gtx
        if rxterm:
            a[rx][rx] += grx
    return solve_linear(a, b)


def normalize_package_class(value: str | None) -> str:
    text = (value or "").lower().replace("-", "_").replace(" ", "_")
    if "advanced" in text:
        return "advanced_package"
    return "standard_package"


def vtf_conditions(package_class: str) -> list[bool]:
    if normalize_package_class(package_class) == "advanced_package":
        return [True]
    return [True, False]


def ucie_vtf_limits(
    data_rate_gbps: float,
    package_class: str,
    rxterm: bool,
    loss_db: float,
    loading: dict[str, float],
) -> dict[str, object]:
    package_class = normalize_package_class(package_class)
    if package_class == "advanced_package":
        if data_rate_gbps <= 16.0:
            return {
                "table": "5-17",
                "condition": "advanced_package",
                "loss_limit_db": -3.0,
                "xt_limit_db": min(1.5 * loss_db - 21.5, -23.0),
                "xt_equation": "XT(fN) < 1.5*L(fN)-21.5 and XT(fN) < -23",
            }
        return {
            "table": "5-17",
            "condition": "advanced_package",
            "loss_limit_db": -5.0,
            "xt_limit_db": min(1.5 * loss_db - 19.0, -24.0),
            "xt_equation": "XT(fN) < 1.5*L(fN)-19 and XT(fN) < -24",
        }
    if rxterm:
        if data_rate_gbps <= 16.0:
            xt_limit = min(3.0 * loss_db - 11.5, -25.0)
            xt_equation = "XT(fN) < 3*L(fN)-11.5 and XT(fN) < -25"
        else:
            xt_limit = min(2.5 * loss_db - 10.0, -26.0)
            xt_equation = "XT(fN) < 2.5*L(fN)-10 and XT(fN) < -26"
        return {
            "table": "5-24",
            "condition": "rxterm",
            "loss_limit_db": loading["rxterm_loss_limit_db"],
            "xt_limit_db": xt_limit,
            "xt_equation": xt_equation,
        }
    return {
        "table": "5-25",
        "condition": "no_rxterm",
        "loss_limit_db": loading["no_rxterm_loss_limit_db"],
        "xt_limit_db": min(loading["no_rxterm_xt_a"] * loss_db + loading["no_rxterm_xt_b"], loading["no_rxterm_xt_floor_db"]),
        "xt_equation": (
            f"XT(fN) < {loading['no_rxterm_xt_a']:g}*L(fN){loading['no_rxterm_xt_b']:+g} "
            f"and XT(fN) < {loading['no_rxterm_xt_floor_db']:g}"
        ),
    }


def run_vtf(
    s_matrix: list[list[complex]],
    zref: float,
    freq_ghz: float,
    data_rate_gbps: float,
    lane_count: int,
    rxterm: bool,
    package_class: str = "standard_package",
) -> list[dict[str, object]]:
    loading = ucie_loading(data_rate_gbps)
    y_channel = s_to_y(s_matrix, zref)
    rows = []
    for victim in range(lane_count):
        victim_rx = 2 * victim + 1
        victim_solution = solve_loaded_channel(y_channel, freq_ghz, victim, rxterm, lane_count, loading)
        loss_db = db20(victim_solution[victim_rx])
        xt_ratios = []
        xt_items = []
        for aggressor in range(lane_count):
            if aggressor == victim:
                continue
            solution = solve_loaded_channel(y_channel, freq_ghz, aggressor, rxterm, lane_count, loading)
            ratio = solution[victim_rx]
            xt_ratios.append(ratio)
            xt_items.append({"aggressor_lane": aggressor, "db": db20(ratio)})
        xt_db = db10_power(xt_ratios)
        worst = max(xt_items, key=lambda item: item["db"]) if xt_items else None
        limits = ucie_vtf_limits(data_rate_gbps, package_class, rxterm, loss_db, loading)
        rows.append(
            {
                "table": limits["table"],
                "condition": limits["condition"],
                "victim_lane": victim,
                "l_fn_db": loss_db,
                "loss_limit_db": limits["loss_limit_db"],
                "loss_pass": loss_db > float(limits["loss_limit_db"]),
                "xt_fn_db": xt_db,
                "xt_limit_db": limits["xt_limit_db"],
                "xt_pass": xt_db < float(limits["xt_limit_db"]),
                "xt_limit_equation": limits["xt_equation"],
                "worst_single_xt": worst,
                "aggressor_count": len(xt_ratios),
            }
        )
    return rows


def build_vtf_frequency_curves(
    freqs: list[float],
    mats: list[list[list[complex]]],
    zref: float,
    data_rate_gbps: float,
    lane_count: int,
    package_class: str = "standard_package",
) -> list[dict[str, object]]:
    curves: list[dict[str, object]] = []
    for freq_ghz, s_matrix in zip(freqs, mats):
        for rxterm in vtf_conditions(package_class):
            rows = run_vtf(s_matrix, zref, freq_ghz, data_rate_gbps, lane_count, rxterm=rxterm, package_class=package_class)
            for row in rows:
                curves.append(
                    {
                        "frequency_ghz": freq_ghz,
                        "condition": row["condition"],
                        "victim_lane": row["victim_lane"],
                        "l_db": row["l_fn_db"],
                        "loss_limit_db": row["loss_limit_db"],
                        "xt_db": row["xt_fn_db"],
                        "xt_limit_db": row["xt_limit_db"],
                        "table": row["table"],
                        "xt_limit_equation": row["xt_limit_equation"],
                    }
                )
    return curves


def write_vtf_plots(payload: dict[str, object], reports: Path) -> dict[str, str]:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except Exception as exc:
        return {"plot_error": f"matplotlib unavailable: {exc}"}

    curves = payload.get("frequency_curves", [])
    if not isinstance(curves, list) or not curves:
        return {"plot_error": "frequency_curves missing"}

    reports.mkdir(parents=True, exist_ok=True)
    conditions = sorted({str(row.get("condition")) for row in curves if row.get("condition")})
    if "rxterm" in conditions:
        conditions = [item for item in ["rxterm", "no_rxterm"] if item in conditions]
    condition_titles = {
        "rxterm": "Standard Package: With Rx Termination",
        "no_rxterm": "Standard Package: No Rx Termination",
        "advanced_package": "Advanced Package",
    }
    outputs: dict[str, str] = {}

    def plot_metric(metric_key: str, limit_key: str, ylabel: str, title: str, filename: str) -> Path:
        fig, axes = plt.subplots(1, len(conditions), figsize=(7.0 * len(conditions), 5.0), sharey=False)
        if len(conditions) == 1:
            axes = [axes]
        for ax, condition in zip(axes, conditions):
            condition_rows = [row for row in curves if row.get("condition") == condition]
            lanes = sorted({int(row["victim_lane"]) for row in condition_rows})
            for lane in lanes:
                lane_rows = sorted(
                    [row for row in condition_rows if int(row["victim_lane"]) == lane],
                    key=lambda row: float(row["frequency_ghz"]),
                )
                ax.plot(
                    [float(row["frequency_ghz"]) for row in lane_rows],
                    [float(row[metric_key]) for row in lane_rows],
                    linewidth=1.0,
                    alpha=0.85,
                    label=f"L{lane}",
                )
            if condition_rows:
                first = condition_rows[0]
                if limit_key == "xt_limit_db":
                    limit_rows = sorted(
                        [row for row in condition_rows if int(row["victim_lane"]) == lanes[0]],
                        key=lambda row: float(row["frequency_ghz"]),
                    )
                    ax.plot(
                        [float(row["frequency_ghz"]) for row in limit_rows],
                        [float(row[limit_key]) for row in limit_rows],
                        color="black",
                        linestyle="--",
                        linewidth=1.6,
                        label="Spec limit",
                    )
                else:
                    ax.axhline(float(first[limit_key]), color="black", linestyle="--", linewidth=1.6, label="Spec limit")
            ax.axvline(float(payload.get("nyquist_ghz", 0.0)), color="red", linestyle=":", linewidth=1.4, label="Nyquist")
            ax.set_title(condition_titles.get(condition, condition))
            ax.set_xlabel("Frequency (GHz)")
            ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=7, ncol=2)
        fig.suptitle(title)
        path = reports / filename
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        return path

    loss_png = plot_metric("l_db", "loss_limit_db", "VTF Loss L(f) (dB)", "VTF Loss vs Frequency", "ads_vtf_loss_vs_frequency.png")
    xt_png = plot_metric("xt_db", "xt_limit_db", "VTF Crosstalk XT(f) (dB)", "VTF Crosstalk vs Frequency", "ads_vtf_crosstalk_vs_frequency.png")
    outputs["vtf_loss_png"] = str(loss_png)
    outputs["vtf_crosstalk_png"] = str(xt_png)

    pdf_path = reports / "ads_full_vtf_verification_report.pdf"
    with PdfPages(pdf_path) as pdf:
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_subplot(111)
        ax.axis("off")
        pf = payload.get("pass_fail", {})
        lines = [
            "ADS Full VTF Verification Report",
            "",
            f"Touchstone: {payload.get('touchstone')}",
            f"Data rate: {payload.get('data_rate_gbps')} GT/s",
            f"Nyquist: {payload.get('nyquist_ghz')} GHz",
            f"Evaluated sample: {payload.get('sample_frequency_ghz')} GHz ({payload.get('sample_interpolation')})",
            f"Lane count: {payload.get('lane_count')}",
            "",
            f"Package class: {payload.get('package_class')}",
            f"Table 5-17 advanced-package pass: {pf.get('table_5_17_advanced_package')}",
            f"Table 5-24 standard rx-term pass: {pf.get('table_5_24_rxterm')}",
            f"Table 5-25 standard no-rx-term pass: {pf.get('table_5_25_no_rxterm')}",
            f"Overall VTF pass: {pf.get('overall_vtf')}",
            "",
            "The following pages plot measured frequency-domain results against spec limits.",
            "Eye/mask/BERContour is generated by the ChannelSim bench, not by this AC/VTF report.",
        ]
        ax.text(0.04, 0.96, "\n".join(lines), va="top", ha="left", fontsize=11, family="monospace")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for image_path, title in [(loss_png, "VTF Loss vs Frequency"), (xt_png, "VTF Crosstalk vs Frequency")]:
            img = plt.imread(image_path)
            fig, ax = plt.subplots(figsize=(11, 8.5))
            ax.imshow(img)
            ax.axis("off")
            ax.set_title(title)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    outputs["vtf_pdf"] = str(pdf_path)
    return outputs


def make_ads_netlist(
    touchstone_name: str,
    lane_count: int,
    data_rate_gbps: float,
    active_lane: int,
    rxterm: bool,
    start_ghz: float,
    stop_ghz: float,
    step_ghz: float,
) -> str:
    loading = ucie_loading(data_rate_gbps)
    crx_pf = loading["crx_term_pf"] if rxterm else loading["crx_no_term_pf"]
    nodes = []
    for lane in range(lane_count):
        nodes.extend([f"tx{lane}", f"rx{lane}"])
    lines = [
        'Options ResourceUsage=yes UseNutmegFormat=no EnableOptim=no TopDesignName="sipi_harness:ads_full_vtf:schematic" DcopOutputNodeVoltages=yes DcopOutputPinCurrents=yes',
        'AC:AC1 CalcNoise=no SortNoise=0 IncludePortNoise=yes BandwidthForNoise=1 Hz FreqConversion=no UseFiniteDiff=no StatusLevel=2 OutputBudgetIV=no DevOpPtLevel=0 SweepVar="freq" SweepPlan="AC1_stim" OutputPlan="AC1_Output"',
        f"SweepPlan: AC1_stim Start={start_ghz:g} GHz Stop={stop_ghz:g} GHz Step={step_ghz:g} GHz",
        'OutputPlan:AC1_Output Type="Output" UseNodeNestLevel=yes NodeNestLevel=2 UseEquationNestLevel=yes EquationNestLevel=2 UseSavedEquationNestLevel=yes SavedEquationNestLevel=2 UseDeviceCurrentNestLevel=no DeviceCurrentNestLevel=0 DeviceCurrentDeviceType="All" DeviceCurrentSymSyntax=yes UseCurrentNestLevel=yes CurrentNestLevel=999 UseDeviceVoltageNestLevel=no DeviceVoltageNestLevel=0 DeviceVoltageDeviceType="All"',
        f'SnP:SNP_CHANNEL {" ".join(nodes)} File="{touchstone_name}" Type="touchstone" NumPorts={2 * lane_count} InterpMode="linear" InterpDom="rectangular" ExtrapMode="constant" Temp=25 CheckPassivity=yes',
    ]
    for lane in range(lane_count):
        tx = f"tx{lane}"
        rx = f"rx{lane}"
        if lane == active_lane:
            lines.append(f'V_Source:SRC_L{lane} src{lane} 0 Type="V_AC" Vdc=0.0 V Vac=polar(1,0) V Freq=freq V_Noise=0 uV SaveCurrent=1')
            lines.append(f"R:R_TX_SRC_L{lane} src{lane} {tx} R=30 Ohm")
        else:
            lines.append(f"R:R_TX_TERM_L{lane} {tx} 0 R=30 Ohm")
        lines.append(f"C:C_TX_L{lane} {tx} 0 C={loading['ctx_pf']:g} pF")
        if rxterm:
            lines.append(f"R:R_RX_L{lane} {rx} 0 R=50 Ohm")
        lines.append(f"C:C_RX_L{lane} {rx} 0 C={crx_pf:g} pF")
    return "\n".join(lines) + "\n"


def run_ads_smoke(netlist: str, out_dir: Path, name: str, data_dir: Path, hpeesof_dir: str) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    netlist_path = out_dir / f"{name}.ckt"
    log_path = out_dir / f"{name}.log"
    netlist_path.write_text(netlist, encoding="utf-8")
    try:
        from keysight.edatoolbox.ads import CircuitSimulator

        simulator = CircuitSimulator(hpeesof_dir=hpeesof_dir)
        result = simulator.run_netlist(
            netlist,
            output_dir=str(out_dir),
            working_dir=str(out_dir),
            output_file=str(log_path),
            netlist_file=str(netlist_path),
            rel_data_dir=str(data_dir),
            dataset_name=name,
        )
        return {
            "name": name,
            "netlist": str(netlist_path),
            "log": str(log_path),
            "return_code": getattr(result, "returncode", None),
            "success": True,
        }
    except Exception as exc:
        return {
            "name": name,
            "netlist": str(netlist_path),
            "log": str(log_path),
            "success": False,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run source-derived ADS VTF verification from a multi-lane Touchstone.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--port-intents", type=Path, required=True)
    parser.add_argument("--data-rate-gbps", type=float, required=True)
    parser.add_argument("--package-class", default="standard_package", choices=["standard_package", "advanced_package", "standard", "advanced"])
    parser.add_argument("--hpeesof-dir", default=os.environ.get("HPEESOF_DIR", r"C:\Program Files\Keysight\ADS2026_Update2"))
    parser.add_argument("--run-ads-smoke", action="store_true")
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()

    args.workspace.mkdir(parents=True, exist_ok=True)
    data_dir = args.workspace / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    local_touchstone = data_dir / args.touchstone.name
    if args.touchstone.resolve() != local_touchstone.resolve():
        shutil.copy2(args.touchstone, local_touchstone)

    freqs, mats, zref, option = parse_touchstone(local_touchstone)
    port_spec = json.loads(args.port_intents.read_text(encoding="utf-8-sig"))
    lane_count = len(port_spec.get("ports", [])) // 2
    nyquist_ghz = args.data_rate_gbps / 2.0
    sample_ghz, s_at_fn, interpolation = interp_matrix(freqs, mats, nyquist_ghz)
    loading = ucie_loading(args.data_rate_gbps)
    package_class = normalize_package_class(args.package_class)

    rows_by_condition: dict[str, list[dict[str, object]]] = {}
    all_rows: list[dict[str, object]] = []
    for rxterm in vtf_conditions(package_class):
        rows = run_vtf(s_at_fn, zref, sample_ghz, args.data_rate_gbps, lane_count, rxterm=rxterm, package_class=package_class)
        if rows:
            rows_by_condition[str(rows[0]["condition"])] = rows
            all_rows.extend(rows)
    frequency_curves = build_vtf_frequency_curves(freqs, mats, zref, args.data_rate_gbps, lane_count, package_class=package_class)

    ads_runs: list[dict[str, object]] = []
    if args.run_ads_smoke:
        step = max((max(freqs) - min(freqs)) / max(len(freqs) - 1, 1), 0.1)
        for rxterm in vtf_conditions(package_class):
            condition = "rxterm" if rxterm else "no_rxterm"
            if package_class == "advanced_package":
                condition = "advanced_package"
            netlist = make_ads_netlist(
                local_touchstone.name,
                lane_count,
                args.data_rate_gbps,
                active_lane=0,
                rxterm=rxterm,
                start_ghz=min(freqs),
                stop_ghz=max(freqs),
                step_ghz=step,
            )
            ads_runs.append(run_ads_smoke(netlist, args.workspace / "ads_runs", f"vtf_{condition}_victim0", data_dir, args.hpeesof_dir))

    payload = {
        "workspace": str(args.workspace),
        "touchstone": str(local_touchstone),
        "touchstone_option": option,
        "zref_ohm": zref,
        "data_rate_gbps": args.data_rate_gbps,
        "package_class": package_class,
        "nyquist_ghz": nyquist_ghz,
        "sample_frequency_ghz": sample_ghz,
        "sample_interpolation": interpolation,
        "frequency_range_ghz": [min(freqs), max(freqs)],
        "lane_count": lane_count,
        "loading_model": {
            "rtx_ohm": 30.0,
            "rrx_ohm": 50.0,
            "ctx_pf": loading["ctx_pf"],
            "rxterm_crx_pf": loading["crx_term_pf"],
            "no_rxterm_crx_pf": loading["crx_no_term_pf"],
        },
        "equations": {
            "loss": "L(f)=20log10(|Vr(f)/Vs(f)|)",
            "crosstalk": "XT(f)=10log10(sum_i(|Vai(f)/Vs(f)|^2)); this x8 case sums the 7 available data-lane aggressors.",
        },
        "results": all_rows,
        "frequency_curves": frequency_curves,
        "pass_fail": {},
        "ads_runs": ads_runs,
        "notes": [
            "ADS smoke runs, when enabled, execute equivalent AC netlists through hpeesofsim for traceability.",
            "Metrics are calculated from the same Touchstone with explicit UCIe Tx/Rx R-C loading using nodal analysis.",
            "L(0) is not evaluated because the exported Touchstone does not include DC; use a DC-capable sweep/export for Table 5-24 L(0).",
            "Eye mask/BERContour is not evaluated by this AC/VTF script; run the ADS ChannelSim bench for eye compliance.",
        ],
    }
    payload["pass_fail"]["table_5_17_advanced_package"] = (
        all(row["loss_pass"] and row["xt_pass"] for row in rows_by_condition.get("advanced_package", []))
        if "advanced_package" in rows_by_condition
        else None
    )
    payload["pass_fail"]["table_5_24_rxterm"] = (
        all(row["loss_pass"] and row["xt_pass"] for row in rows_by_condition.get("rxterm", []))
        if "rxterm" in rows_by_condition
        else None
    )
    payload["pass_fail"]["table_5_25_no_rxterm"] = (
        all(row["loss_pass"] and row["xt_pass"] for row in rows_by_condition.get("no_rxterm", []))
        if "no_rxterm" in rows_by_condition
        else None
    )
    active_pf = [value for value in payload["pass_fail"].values() if value is not None]
    payload["pass_fail"]["overall_vtf"] = all(active_pf) if active_pf else False

    out_json = args.out_json or (args.workspace / "reports" / "ads_full_vtf_verification.json")
    out_md = args.out_md or (args.workspace / "reports" / "ads_full_vtf_verification.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    payload["plots"] = write_vtf_plots(payload, out_json.parent)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# ADS Full VTF Verification",
        "",
        f"- Touchstone: `{local_touchstone}`",
        f"- Package class: {package_class}",
        f"- Data rate: {args.data_rate_gbps:g} GT/s; Nyquist: {nyquist_ghz:g} GHz",
        f"- Evaluated frequency: {sample_ghz:g} GHz ({interpolation})",
        f"- Frequency range: {min(freqs):g} to {max(freqs):g} GHz",
        f"- Loading: Tx 30 ohm + {loading['ctx_pf']:g} pF; Rx-term 50 ohm + {loading['crx_term_pf']:g} pF; no-Rx-term Rx {loading['crx_no_term_pf']:g} pF",
        f"- Table 5-17 advanced-package overall: {payload['pass_fail']['table_5_17_advanced_package']}",
        f"- Table 5-24 standard rx-term overall: {payload['pass_fail']['table_5_24_rxterm']}",
        f"- Table 5-25 standard no-rx-term overall: {payload['pass_fail']['table_5_25_no_rxterm']}",
        f"- Overall VTF: {payload['pass_fail']['overall_vtf']}",
        f"- Plot report: `{payload['plots'].get('vtf_pdf', payload['plots'].get('plot_error', 'missing'))}`",
        "",
        "| Condition | Victim | L(fN) dB | L limit | Loss | XT(fN) dB | XT limit | XT | Worst aggressor | Aggressors |",
        "|---|---:|---:|---:|:---:|---:|---:|:---:|---|---:|",
    ]
    for row in all_rows:
        worst = row["worst_single_xt"] or {}
        lines.append(
            f"| {row['condition']} | {row['victim_lane']} | {row['l_fn_db']:.3f} | {row['loss_limit_db']:.3f} | "
            f"{row['loss_pass']} | {row['xt_fn_db']:.3f} | {row['xt_limit_db']:.3f} | {row['xt_pass']} | "
            f"L{worst.get('aggressor_lane', '-')} {float(worst.get('db', 0.0)):.3f} dB | {row['aggressor_count']} |"
        )
    if ads_runs:
        lines.extend(["", "## ADS hpeesofsim Smoke Runs", ""])
        for run in ads_runs:
            lines.append(f"- {run['name']}: success={run['success']}, netlist=`{run['netlist']}`, log=`{run['log']}`")
            if not run.get("success"):
                lines.append(f"  - error: {run.get('error')}")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- VTF loss follows UCIe Eq. 5-5: `20log10(|Vr/Vs|)`.",
            "- VTF crosstalk follows UCIe Eq. 5-7 power-sum over available x8 data-lane aggressors.",
            "- Eye mask/BERContour requires the ADS ChannelSim bench and is not part of this AC/VTF run.",
        ]
    )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload["pass_fail"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
