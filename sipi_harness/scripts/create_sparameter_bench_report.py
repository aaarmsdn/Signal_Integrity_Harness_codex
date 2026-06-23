from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


SPEC_DEFINED_BENCH_PATTERNS = {
    "voltage_transfer_function": [
        r"\bvtf\b",
        r"voltage\s+transfer\s+function",
        r"\bl\(fn\)",
        r"\bloss\s*\(db\)",
    ],
    "spec_crosstalk_equation": [
        r"\bxt\(fn\)",
        r"power\s+sum",
        r"crosstalk\s+power",
        r"aggressor",
    ],
    "explicit_loading_model": [
        r"\brtx\b",
        r"\bctx\b",
        r"\brrx\b",
        r"\bcrx\b",
        r"loading\s+model",
        r"source\s*/\s*receiver\s+model",
    ],
    "eye_or_ber": [
        r"eye\s+diagram",
        r"eye\s+mask",
        r"ber\s*contour",
        r"\bber\b",
        r"bathtub",
        r"jitter",
        r"ultra[- ]low\s+ber",
    ],
}


def read_text_if_exists(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def infer_case_dir(workspace: Path) -> Path | None:
    for parent in workspace.parents:
        if parent.name.lower() in {"bench", "ads"} and parent.parent.exists():
            return parent.parent
    return None


def collect_strategy_text(workspace: Path, strategy: Path | None, manifest: Path | None) -> tuple[str, list[str]]:
    paths: list[Path] = []
    if strategy:
        paths.append(strategy)
    if manifest:
        paths.append(manifest)
    case_dir = infer_case_dir(workspace)
    if case_dir:
        paths.extend(
            [
                case_dir / "strategy" / "design_strategy.yaml",
                case_dir / "strategy" / "wiki_fusion_input.json",
                case_dir / "manifest.json",
            ]
        )
        paths.extend(sorted((case_dir / "spec_evidence").glob("**/*.json"))[:50])
    seen: set[Path] = set()
    chunks: list[str] = []
    used: list[str] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        chunks.append(read_text_if_exists(resolved))
        used.append(str(resolved))
    return "\n".join(chunks), used


def detect_spec_defined_bench_requirements(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    detected: dict[str, list[str]] = {}
    for family, patterns in SPEC_DEFINED_BENCH_PATTERNS.items():
        matches = [pattern for pattern in patterns if re.search(pattern, lowered, re.IGNORECASE)]
        if matches:
            detected[family] = matches
    return detected


def first_float(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return None


def infer_spec_overlay(strategy_text: str, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract candidate plotting limits from case strategy/spec evidence text.

    This is intentionally conservative: values are tagged as candidate overlay
    limits for plots. Compliance still requires reviewed tier-0 evidence and a
    spec-defined bench.
    """
    text = strategy_text or ""
    data_rate = first_float([r"(\d+(?:\.\d+)?)\s*(?:gbps|gt/s)"], text)
    nyquist = data_rate / 2.0 if data_rate else None
    il_limit = first_float([r"L\s*\(\s*fN\s*\)\s*>\s*(-?\d+(?:\.\d+)?)"], text)
    xt_direct = first_float([r"XT\s*\(\s*fN\s*\)\s*<\s*(-?\d+(?:\.\d+)?)"], text)
    xt_expr_limit = None
    expr = re.search(
        r"XT\s*\(\s*fN\s*\)\s*<\s*(\d+(?:\.\d+)?)\s*\*?\s*L\s*\(\s*fN\s*\)\s*-\s*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if expr and il_limit is not None:
        xt_expr_limit = float(expr.group(1)) * il_limit - float(expr.group(2))
    xt_limit = None
    if xt_direct is not None and xt_expr_limit is not None:
        xt_limit = min(xt_direct, xt_expr_limit)
    elif xt_direct is not None:
        xt_limit = xt_direct
    elif xt_expr_limit is not None:
        xt_limit = xt_expr_limit
    eye_height_mv = first_float(
        [
            r"eye\s+height[^\n\r\d]*(\d+(?:\.\d+)?)\s*mV",
            r"height\s*>?=\s*(\d+(?:\.\d+)?)\s*mV",
        ],
        text,
    )
    eye_width_ui = first_float(
        [
            r"eye\s+width[^\n\r\d]*(\d+(?:\.\d+)?)\s*UI",
            r"width\s*>?=\s*(\d+(?:\.\d+)?)\s*UI",
        ],
        text,
    )
    freq_range = metrics.get("frequency_ghz", []) if metrics else []
    if nyquist is None and freq_range:
        nyquist = max(freq_range) / 3.0
    return {
        "source": "strategy_or_spec_evidence_text",
        "status": "candidate_overlay_not_compliance",
        "data_rate_gbps": data_rate,
        "nyquist_ghz": nyquist,
        "insertion_loss_min_db_at_fn": il_limit,
        "crosstalk_max_db_at_fn": xt_limit,
        "eye_height_mv": eye_height_mv,
        "eye_width_ui": eye_width_ui,
        "notes": [
            "Overlay limits are extracted candidates for visualization.",
            "Compliance requires reviewed tier-0 evidence and the exact spec bench/loading model.",
        ],
    }


def load_eye_result(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    points = data.get("contour_points") or data.get("ber_contour_points") or data.get("points")
    if points and isinstance(points, list):
        normalized = []
        for item in points:
            if isinstance(item, dict):
                x = item.get("x_ui", item.get("time_ui", item.get("x")))
                y = item.get("y_v", item.get("voltage_v", item.get("y")))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                x, y = item[0], item[1]
            else:
                continue
            try:
                normalized.append([float(x), float(y)])
            except Exception:
                continue
        data["contour_points"] = normalized
    return data


def db20(value: complex) -> float:
    return 20 * math.log10(max(abs(value), 1e-300))


def db10_power(values: list[complex]) -> float | None:
    if not values:
        return None
    return 10 * math.log10(max(sum(abs(v) ** 2 for v in values), 1e-300))


def infer_port_count(path: Path) -> int:
    match = re.search(r"\.s(\d+)p$", path.name, re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot infer Touchstone port count from extension: {path}")
    return int(match.group(1))


def parse_touchstone(path: Path) -> tuple[list[float], list[list[list[complex]]], str]:
    ports = infer_port_count(path)
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
            for c in range(ports):
                for r in range(ports):
                    a, b = values[idx], values[idx + 1]
                    idx += 2
                    if fmt == "RI":
                        mat[r][c] = complex(a, b)
                    elif fmt == "DB":
                        mag = 10 ** (a / 20)
                        mat[r][c] = mag * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
                    else:
                        mat[r][c] = a * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
            mats.append(mat)
    if not freqs:
        raise RuntimeError(f"No S-parameter data rows parsed from {path}")
    return freqs, mats, option


def sequential_pairs(port_count: int) -> list[tuple[int, int]]:
    if port_count < 2:
        return []
    return [(idx, idx + 1) for idx in range(0, port_count - 1, 2)]


def build_metrics(freqs: list[float], mats: list[list[list[complex]]], port_count: int) -> dict[str, Any]:
    pairs = sequential_pairs(port_count)
    lanes = []
    for lane, (near, far) in enumerate(pairs):
        il = [db20(mat[far][near]) for mat in mats]
        rl_near = [db20(mat[near][near]) for mat in mats]
        rl_far = [db20(mat[far][far]) for mat in mats]
        xt_power = []
        worst_single = []
        for mat in mats:
            terms = []
            for other_lane, (other_near, other_far) in enumerate(pairs):
                if other_lane == lane:
                    continue
                terms.extend([mat[other_near][near], mat[other_far][near]])
            xt_power.append(db10_power(terms))
            worst_single.append(max((db20(term) for term in terms), default=None))
        lanes.append(
            {
                "lane": lane,
                "ports_1based": [near + 1, far + 1],
                "insertion_loss_db": il,
                "return_loss_near_db": rl_near,
                "return_loss_far_db": rl_far,
                "crosstalk_power_sum_db": xt_power,
                "worst_single_crosstalk_db": worst_single,
                "worst_insertion_loss_db": min(il),
                "worst_return_loss_db": max(max(rl_near), max(rl_far)),
                "worst_crosstalk_power_sum_db": max((v for v in xt_power if v is not None), default=None),
            }
        )
    return {
        "frequency_ghz": freqs,
        "port_count": port_count,
        "lane_pairing": "sequential_pairs_1_2_3_4",
        "lane_count": len(lanes),
        "lanes": lanes,
        "overall": {
            "worst_insertion_loss_db": min((lane["worst_insertion_loss_db"] for lane in lanes), default=None),
            "worst_return_loss_db": max((lane["worst_return_loss_db"] for lane in lanes), default=None),
            "worst_crosstalk_power_sum_db": max(
                (lane["worst_crosstalk_power_sum_db"] for lane in lanes if lane["worst_crosstalk_power_sum_db"] is not None),
                default=None,
            ),
        },
    }


def create_ads_de_workspace(workspace: Path, touchstone_name: str, port_count: int) -> dict[str, Any]:
    try:
        import keysight.ads.de as de
        from keysight.ads.de import db_uu as db
    except Exception as exc:
        return {"created": False, "method": "ads_de", "detail": f"ADS DE import failed: {exc}"}

    lib_name = "sipi_sparameter_bench_lib"
    cell_name = "sparameter_sanity"
    try:
        if de.workspace_is_open():
            de.close_workspace()
        if workspace.exists():
            shutil.rmtree(workspace)
        ws = de.create_workspace(workspace)
        ws.open()
        data_dir = workspace / "data"
        data_dir.mkdir(exist_ok=True)
        lib_path = workspace / lib_name
        de.create_new_library(lib_name, lib_path)
        ws.add_library(lib_name, lib_path, de.LibraryMode.NON_SHARED)
        design = db.create_schematic(f"{lib_name}:{cell_name}:schematic")
        fixed_ports = {2, 4, 6, 8, 10, 12, 16}
        symbol_name = f"S{port_count}P" if port_count in fixed_ports else "SnP"
        snp = design.add_instance(("ads_datacmps", symbol_name, "symbol"), (0, 0), name="SnP_Channel")
        for key in ("File", "FileName", "TSfile"):
            try:
                snp.parameters[key].value = touchstone_name
            except Exception:
                pass
        try:
            snp.parameters["NumPorts"].value = str(port_count)
        except Exception:
            pass
        labeled_pins: list[dict[str, Any]] = []
        try:
            terms = list(snp.get_inst_term_iter())
            by_number = {}
            for term in terms:
                try:
                    by_number[int(term.term_number)] = term
                except Exception:
                    pass
            if not by_number:
                raise RuntimeError("SnP symbol exposes no term_number values; cannot prove port order")

            def assign_term(term_number: int, net_name: str, pin_name: int | str) -> dict[str, Any]:
                term = by_number.get(term_number)
                if term is None:
                    return {"pin": pin_name, "net": net_name, "term_number": term_number, "ok": False, "reason": "term_number not found"}
                net = design.find_or_add_net(net_name)
                try:
                    term.net = net
                except Exception:
                    pass
                pin = next(iter(term.get_inst_pin_iter()))
                try:
                    pin.net = net
                except Exception:
                    pass
                x = float(pin.bbox.x1)
                y = float(pin.bbox.y1)
                return {"pin": pin_name, "net": net_name, "term_number": term_number, "x": x, "y": y, "ok": True}

            for port in range(1, port_count + 1):
                labeled_pins.append(assign_term(port, f"p{port}", port))
            labeled_pins.append(assign_term(port_count + 1, "gnd!", "ref"))
        except Exception as exc:
            labeled_pins.append({"ok": False, "error": str(exc)})
        design.save_design()
        netlist_status: dict[str, Any]
        try:
            netlist = design.create_netlist()
            netlist_path = workspace / "reports" / "sparameter_sanity.netlist.log"
            netlist_path.parent.mkdir(exist_ok=True)
            netlist_path.write_text(netlist, encoding="utf-8", errors="replace")
            netlist_status = {"created": True, "path": str(netlist_path), "bytes": len(netlist.encode("utf-8", errors="replace"))}
        except Exception as exc:
            netlist_status = {"created": False, "error": str(exc)}
        ws.close()
        return {
            "created": True,
            "method": "ads_de",
            "library": lib_name,
            "cell": cell_name,
            "schematic": f"{lib_name}:{cell_name}:schematic",
            "symbol": f"ads_datacmps:{symbol_name}",
            "labeled_pins": labeled_pins,
            "netlist": netlist_status,
            "detail": "Created ADS workspace and SnP inspection schematic with pin labels and netlist audit.",
        }
    except Exception as exc:
        try:
            if de.workspace_is_open():
                de.close_workspace()
        except Exception:
            pass
        return {"created": False, "method": "ads_de", "detail": f"ADS DE workspace generation failed: {exc}"}


def ensure_workspace_dirs(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "data").mkdir(exist_ok=True)
    (workspace / "reports").mkdir(exist_ok=True)


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, title, fontsize=15, weight="bold", va="top")
    y = 0.90
    for line in lines:
        if y < 0.07:
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.08, 0.95, f"{title} (continued)", fontsize=15, weight="bold", va="top")
            y = 0.90
        fig.text(0.08, y, str(line), fontsize=8.5, family="monospace", va="top")
        y -= 0.026
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def write_plots(
    workspace: Path,
    metrics: dict[str, Any],
    spec_overlay: dict[str, Any] | None = None,
    eye_result: dict[str, Any] | None = None,
) -> dict[str, str]:
    reports = workspace / "reports"
    freqs = metrics["frequency_ghz"]
    spec_overlay = spec_overlay or {}
    plots: dict[str, str] = {}

    fig, ax = plt.subplots(figsize=(10, 6))
    for lane in metrics["lanes"]:
        ax.plot(freqs, lane["insertion_loss_db"], label=f"L{lane['lane']} IL S{lane['ports_1based'][1]}{lane['ports_1based'][0]}")
    ax.set_title("Insertion Loss")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude (dB)")
    ax.grid(True, linewidth=0.3)
    ax.legend(fontsize=8)
    path = reports / "sparameter_insertion_loss.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    plots["insertion_loss_png"] = str(path)

    fig, ax = plt.subplots(figsize=(10, 6))
    for lane in metrics["lanes"]:
        ax.plot(freqs, lane["return_loss_near_db"], label=f"L{lane['lane']} near S{lane['ports_1based'][0]}{lane['ports_1based'][0]}")
        ax.plot(freqs, lane["return_loss_far_db"], linestyle="--", label=f"L{lane['lane']} far S{lane['ports_1based'][1]}{lane['ports_1based'][1]}")
    ax.set_title("Return Loss")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("Magnitude (dB)")
    ax.grid(True, linewidth=0.3)
    ax.legend(fontsize=7)
    path = reports / "sparameter_return_loss.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    plots["return_loss_png"] = str(path)

    if any(any(value is not None for value in lane["crosstalk_power_sum_db"]) for lane in metrics["lanes"]):
        fig, ax = plt.subplots(figsize=(10, 6))
        for lane in metrics["lanes"]:
            values = [float("nan") if value is None else value for value in lane["crosstalk_power_sum_db"]]
            ax.plot(freqs, values, label=f"L{lane['lane']} power-sum XT")
        ax.set_title("Crosstalk Power Sum")
        ax.set_xlabel("Frequency (GHz)")
        ax.set_ylabel("Magnitude (dB)")
        ax.grid(True, linewidth=0.3)
        ax.legend(fontsize=8)
        path = reports / "sparameter_crosstalk.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        plots["crosstalk_png"] = str(path)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), sharex=True)
    for lane in metrics["lanes"]:
        axes[0].plot(freqs, lane["insertion_loss_db"], label=f"L{lane['lane']}")
    il_limit = spec_overlay.get("insertion_loss_min_db_at_fn")
    nyquist = spec_overlay.get("nyquist_ghz")
    if il_limit is not None:
        axes[0].axhline(float(il_limit), color="crimson", linestyle="--", label=f"Spec min @ fN {float(il_limit):g} dB")
    if nyquist is not None:
        axes[0].axvline(float(nyquist), color="black", linestyle=":", label=f"fN {float(nyquist):g} GHz")
    axes[0].set_title("Insertion Loss vs Spec")
    axes[0].set_xlabel("Frequency (GHz)")
    axes[0].set_ylabel("Magnitude (dB)")
    axes[0].grid(True, linewidth=0.3)
    axes[0].legend(fontsize=7)

    has_xt = any(any(value is not None for value in lane["crosstalk_power_sum_db"]) for lane in metrics["lanes"])
    if has_xt:
        for lane in metrics["lanes"]:
            values = [float("nan") if value is None else value for value in lane["crosstalk_power_sum_db"]]
            axes[1].plot(freqs, values, label=f"L{lane['lane']}")
    xt_limit = spec_overlay.get("crosstalk_max_db_at_fn")
    if xt_limit is not None:
        axes[1].axhline(float(xt_limit), color="crimson", linestyle="--", label=f"Spec max @ fN {float(xt_limit):g} dB")
    if nyquist is not None:
        axes[1].axvline(float(nyquist), color="black", linestyle=":", label=f"fN {float(nyquist):g} GHz")
    axes[1].set_title("Crosstalk vs Spec")
    axes[1].set_xlabel("Frequency (GHz)")
    axes[1].set_ylabel("Magnitude (dB)")
    axes[1].grid(True, linewidth=0.3)
    axes[1].legend(fontsize=7)
    fig.suptitle("Result vs Spec Overlay (candidate limits; compliance requires exact reviewed bench)")
    path = reports / "result_vs_spec_overlay.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    plots["result_vs_spec_overlay_png"] = str(path)

    eye_height_mv = spec_overlay.get("eye_height_mv")
    eye_width_ui = spec_overlay.get("eye_width_ui")
    eye_result = eye_result or {}
    if eye_height_mv is not None or eye_width_ui is not None or eye_result:
        height_v = float(eye_height_mv or 0.0) / 1000.0
        width_ui = float(eye_width_ui or 0.0)
        fig, ax = plt.subplots(figsize=(8, 5.5))
        ax.set_title("Eye Diagram / BER Contour vs Rectangular Mask")
        ax.set_xlabel("Time (UI)")
        ax.set_ylabel("Voltage (V)")
        ax.set_xlim(-0.8, 0.8)
        y_margin = max(0.08, height_v * 2.5)
        ax.set_ylim(-y_margin, y_margin)
        if width_ui > 0 and height_v > 0:
            x0 = -width_ui / 2.0
            y0 = -height_v / 2.0
            rect_x = [x0, x0 + width_ui, x0 + width_ui, x0, x0]
            rect_y = [y0, y0, y0 + height_v, y0 + height_v, y0]
            ax.plot(rect_x, rect_y, color="crimson", linewidth=2.0, label=f"Spec mask {width_ui:g} UI x {height_v * 1000:g} mV")
        contour = eye_result.get("contour_points") or []
        if contour:
            xs = [float(item[0]) for item in contour]
            ys = [float(item[1]) for item in contour]
            ax.plot(xs, ys, color="royalblue", linewidth=1.8, label="ADS BERContour")
            if xs and ys:
                ax.set_xlim(min(-0.8, min(xs) - 0.05), max(0.8, max(xs) + 0.05))
                y_span = max(abs(min(ys)), abs(max(ys)), height_v * 1.5, 0.08)
                ax.set_ylim(-y_span, y_span)
            measured_width = eye_result.get("width_ui") or eye_result.get("contour_width_ui")
            measured_height = eye_result.get("height_v") or eye_result.get("contour_height_v")
            status = []
            if measured_width is not None and width_ui:
                status.append(f"width {float(measured_width):g} UI {'PASS' if float(measured_width) >= width_ui else 'FAIL'}")
            if measured_height is not None and height_v:
                status.append(f"height {float(measured_height) * 1000:g} mV {'PASS' if float(measured_height) >= height_v else 'FAIL'}")
            if status:
                ax.text(
                    0.02,
                    0.03,
                    " / ".join(status),
                    transform=ax.transAxes,
                    fontsize=9,
                    bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": "0.6"},
                )
        else:
            ax.text(
                0.0,
                0.0,
                "ADS BERContour data not present in this report\n"
                "Use ChannelSim/Eye Probe contour variables for compliance.",
                ha="center",
                va="center",
                fontsize=10,
                bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "0.6"},
            )
        ax.grid(True, linewidth=0.3)
        ax.legend(fontsize=8, loc="upper right")
        path = reports / "eye_mask_overlay.png"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        plots["eye_mask_overlay_png"] = str(path)

    pdf_path = reports / "sparameter_bench_report.pdf"
    with PdfPages(pdf_path) as pdf:
        add_text_page(
            pdf,
            "S-Parameter Bench Report",
            [
                f"Workspace: {workspace}",
                f"Port count: {metrics['port_count']}",
                f"Lane pairing: {metrics['lane_pairing']}",
                f"Frequency range: {min(freqs):g} GHz to {max(freqs):g} GHz",
                "",
                "This is a spec-neutral fallback report. It plots S-parameter evidence only.",
                "Do not treat this as compliance when the governing spec defines VTF, loaded benches, masks, or other equations.",
                "",
                f"Worst insertion loss: {metrics['overall']['worst_insertion_loss_db']}",
                f"Worst return loss: {metrics['overall']['worst_return_loss_db']}",
                f"Worst crosstalk power sum: {metrics['overall']['worst_crosstalk_power_sum_db']}",
            ],
        )
        for key, image_path in plots.items():
            if key.endswith("_png"):
                img = plt.imread(image_path)
                fig, ax = plt.subplots(figsize=(11.69, 8.27))
                ax.imshow(img)
                ax.axis("off")
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
    plots["pdf"] = str(pdf_path)
    return plots


def write_markdown(workspace: Path, summary: dict[str, Any]) -> Path:
    path = workspace / "reports" / "sparameter_bench_report.md"
    lines = [
        "# S-Parameter Bench Report",
        "",
        f"- Workspace: `{workspace}`",
        f"- Touchstone: `{summary['touchstone']}`",
        f"- Source status: {summary.get('source_status', 'touchstone_input')}",
        f"- ADS schematic created: {summary['ads_workspace'].get('created')}",
        f"- Port count: {summary['metrics']['port_count']}",
        f"- Lane count: {summary['metrics']['lane_count']}",
        f"- Frequency range: {min(summary['metrics']['frequency_ghz']):g} to {max(summary['metrics']['frequency_ghz']):g} GHz",
        "",
        "## Overall",
        "",
        f"- Worst insertion loss: {summary['metrics']['overall']['worst_insertion_loss_db']}",
        f"- Worst return loss: {summary['metrics']['overall']['worst_return_loss_db']}",
        f"- Worst crosstalk power sum: {summary['metrics']['overall']['worst_crosstalk_power_sum_db']}",
        "",
        "## Spec Overlay",
        "",
        f"- Overlay status: {summary.get('spec_overlay', {}).get('status')}",
        f"- Nyquist frequency: {summary.get('spec_overlay', {}).get('nyquist_ghz')} GHz",
        f"- Insertion-loss spec line: {summary.get('spec_overlay', {}).get('insertion_loss_min_db_at_fn')} dB",
        f"- Crosstalk spec line: {summary.get('spec_overlay', {}).get('crosstalk_max_db_at_fn')} dB",
        f"- Eye mask: {summary.get('spec_overlay', {}).get('eye_width_ui')} UI x {summary.get('spec_overlay', {}).get('eye_height_mv')} mV",
        "",
        "## Plots",
        "",
        f"- Result vs spec overlay: `{summary['plots'].get('result_vs_spec_overlay_png')}`",
        f"- Eye mask overlay: `{summary['plots'].get('eye_mask_overlay_png')}`",
        "",
        "This is a spec-neutral fallback. Use spec-specific loaded equations when available.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an ADS/bench workspace and S-parameter fallback report.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--strategy", type=Path, default=None, help="Optional design_strategy.yaml used to block fallback when spec benches exist.")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional case manifest used to block fallback when spec benches exist.")
    parser.add_argument(
        "--eye-result",
        type=Path,
        default=None,
        help="Optional JSON with ADS Eye Probe BERContour points and width/height metrics for mask overlay plotting.",
    )
    parser.add_argument(
        "--allow-missing-eye-contour",
        action="store_true",
        help="Diagnostic only: allow an eye mask annotation without ADS BERContour data. Do not use for spec bench success.",
    )
    parser.add_argument(
        "--allow-spec-neutral-fallback",
        action="store_true",
        help="Allow S-parameter fallback even when strategy/spec evidence indicates exact benches. Use only for diagnostic/sanity reports.",
    )
    parser.add_argument("--fallback-reason", default="", help="Required explanation when --allow-spec-neutral-fallback is used.")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    touchstone = args.touchstone.resolve()
    if not touchstone.exists():
        raise FileNotFoundError(touchstone)

    strategy_text, strategy_sources = collect_strategy_text(
        workspace,
        args.strategy.resolve() if args.strategy else None,
        args.manifest.resolve() if args.manifest else None,
    )
    detected_spec_benches = detect_spec_defined_bench_requirements(strategy_text)
    if detected_spec_benches and not args.allow_spec_neutral_fallback:
        raise RuntimeError(
            "Refusing spec-neutral S-parameter fallback because case evidence indicates "
            f"spec-defined benches: {', '.join(sorted(detected_spec_benches))}. "
            "Implement the exact loading/equation/eye-mask bench or mark Bench blocked. "
            "Use --allow-spec-neutral-fallback with --fallback-reason only for an explicit diagnostic report."
        )
    if args.allow_spec_neutral_fallback and detected_spec_benches and not args.fallback_reason.strip():
        raise RuntimeError("--fallback-reason is required when overriding a detected spec-defined bench.")
    if workspace.exists() and args.overwrite:
        shutil.rmtree(workspace)
    port_count = infer_port_count(touchstone)
    ads_status = create_ads_de_workspace(workspace, touchstone.name, port_count)
    ensure_workspace_dirs(workspace)
    data_dir = workspace / "data"
    touchstone_dst = data_dir / touchstone.name
    if not touchstone_dst.exists():
        shutil.copy2(touchstone, touchstone_dst)

    freqs, mats, option = parse_touchstone(touchstone_dst)
    touchstone_header = "\n".join(
        line.strip()
        for line in touchstone_dst.read_text(encoding="utf-8", errors="replace").splitlines()[:20]
        if line.strip().startswith("!")
    )
    proxy_only = "PROXY_ONLY_NOT_EM" in touchstone_header.upper()
    if proxy_only:
        raise ValueError(
            "Refusing proxy-only Touchstone input. Fix EM export and provide a verified HFSS or measurement Touchstone."
        )
    metrics = build_metrics(freqs, mats, port_count)
    spec_overlay = infer_spec_overlay(strategy_text, metrics)
    eye_result = load_eye_result(args.eye_result.resolve() if args.eye_result else None)
    eye_mask_required = spec_overlay.get("eye_height_mv") is not None or spec_overlay.get("eye_width_ui") is not None
    if eye_mask_required and not eye_result.get("contour_points") and not args.allow_missing_eye_contour:
        raise RuntimeError(
            "Eye/mask spec was detected, but no ADS BERContour result was provided. "
            "Rerun the ADS ChannelSim/Eye Probe bench with Save_Contour=yes, "
            "BERContour=list(<target BER>), Save_WidthAtBER=yes, and Save_HeightAtBER=yes; "
            "then pass the extracted contour JSON with --eye-result. "
            "Use --allow-missing-eye-contour only for an explicitly labeled diagnostic placeholder."
        )
    plots = write_plots(workspace, metrics, spec_overlay, eye_result)
    summary = {
        "workspace": str(workspace),
        "touchstone": str(touchstone_dst),
        "touchstone_option": option,
        "ads_workspace": ads_status,
        "metrics": metrics,
        "spec_overlay": spec_overlay,
        "eye_result": eye_result,
        "eye_contour_required": eye_mask_required,
        "eye_contour_present": bool(eye_result.get("contour_points")),
        "plots": plots,
        "report_type": "spec_neutral_sparameter_fallback",
        "source_status": "verified_touchstone_input",
        "strategy_sources_checked": strategy_sources,
        "detected_spec_defined_benches": detected_spec_benches,
        "fallback_override": bool(args.allow_spec_neutral_fallback),
        "fallback_reason": args.fallback_reason,
        "notes": [
            "Insertion loss uses sequential port pairs: 1->2, 3->4, etc.",
            "Crosstalk is plotted only when at least two sequential lanes are present.",
            "This report is a diagnostic sanity report only when spec-defined VTF/XT/loading/eye/BER benches exist.",
            "This report is evidence, not compliance, unless the selected spec accepts these S-parameter metrics directly.",
        ],
    }
    md_path = write_markdown(workspace, summary)
    summary["markdown"] = str(md_path)
    summary_path = workspace / "reports" / "sparameter_bench_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "summary": str(summary_path), "pdf": plots["pdf"], "ads_workspace": ads_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
