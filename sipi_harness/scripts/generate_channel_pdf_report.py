from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def load_json(path: Path | None) -> dict[str, Any]:
    if path and path.exists() and path.is_file():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {"missing": str(path) if path else "not provided"}


def latest(paths: list[Path], prefer: str | None = None) -> Path | None:
    candidates = [path for path in paths if path.exists()]
    if prefer:
        preferred = [path for path in candidates if prefer in path.name]
        if preferred:
            candidates = preferred
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def latest_recursive(root: Path, pattern: str, prefer: str | None = None) -> Path | None:
    if not root.exists():
        return None
    return latest(list(root.glob(pattern)), prefer=prefer)


def load_evidence(path: Path) -> dict[str, Any]:
    if path.is_file():
        return load_json(path)
    if path.is_dir():
        for name in (
            "reviewed_ucie3_standard_x8_evidence.json",
            "spec_review_queue.json",
            "spec_manifest.json",
            "spec_inventory.json",
        ):
            candidate = path / name
            if candidate.exists():
                data = load_json(candidate)
                data.setdefault("evidence_file", str(candidate))
                return data
    return {"missing": str(path)}


def collect_ads_bench(bench_workspace: Path | None, case_dir: Path) -> dict[str, Any]:
    workspace = bench_workspace
    if workspace is None:
        summary = latest_recursive(case_dir / "bench", "**/ads_bench_from_strategy_summary.json")
        if summary:
            workspace = summary.parent.parent
    if workspace is None:
        return {"workspace": None}

    reports = workspace / "reports"
    loaded_reports = workspace / "loaded_vtf_wrk" / "reports"
    summary_path = reports / "ads_bench_from_strategy_summary.json"
    summary = load_json(summary_path)
    vtf_summary_path = loaded_reports / "ads_full_vtf_verification.json"
    vtf_summary = load_json(vtf_summary_path)
    return {
        "workspace": workspace,
        "summary_path": summary_path if summary_path.exists() else None,
        "summary": summary,
        "vtf_summary_path": vtf_summary_path if vtf_summary_path.exists() else None,
        "vtf_summary": vtf_summary,
        "vtf_loss_png": loaded_reports / "ads_vtf_loss_vs_frequency.png",
        "vtf_xt_png": loaded_reports / "ads_vtf_crosstalk_vs_frequency.png",
        "eye_png": reports / "ads_eye_density_contour_mask.png",
        "eye_pdf": reports / "ads_eye_density_contour_mask_report.pdf",
        "bench_pdf": reports / "ads_bench_final_report.pdf",
        "vtf_pdf": loaded_reports / "ads_full_vtf_verification_report.pdf",
    }


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, title, fontsize=16, weight="bold", va="top")
    y = 0.90
    for line in lines:
        if y < 0.07:
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.08, 0.95, f"{title} (continued)", fontsize=16, weight="bold", va="top")
            y = 0.90
        fig.text(0.08, y, line, fontsize=9, va="top", family="monospace")
        y -= 0.025
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_image_page(pdf: PdfPages, title: str, image_path: Path, caption: str) -> None:
    if not image_path.exists():
        return
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=16, fontweight="bold")
    ax.imshow(mpimg.imread(image_path))
    ax.axis("off")
    fig.text(0.06, 0.04, caption, fontsize=8, family="monospace")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_board_layout_page(pdf: PdfPages, manifest: dict[str, Any]) -> None:
    board = manifest.get("board", {})
    lanes = manifest.get("lanes", [])
    if not lanes:
        return
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.set_title("PCB Channel Layout From Manifest")
    width = float(board.get("widthMm", 0.0) or 0.0)
    height = float(board.get("heightMm", 0.0) or 0.0)
    if width and height:
        ax.add_patch(plt.Rectangle((0, 0), width, height, fill=False, linewidth=1.2, color="black"))
    for lane in lanes:
        x0, y0 = lane.get("start_mm", [None, None])
        x1, y1 = lane.get("end_mm", [None, None])
        if x0 is None or x1 is None:
            continue
        ax.plot([x0, x1], [y0, y1], color="#1f77b4", linewidth=1.1)
        if int(lane.get("lane", 0)) % 4 == 0:
            ax.text(x0 - 0.03, y0, f"L{lane.get('lane')}", fontsize=6, ha="right", va="center")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.grid(True, linewidth=0.25)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_check_plot_page(pdf: PdfPages, check: dict[str, Any]) -> None:
    results = check.get("results", [])
    if not results:
        return
    lanes = [item.get("lane") for item in results]
    loss = [item.get("insertion_loss_db") for item in results]
    xt = [item.get("xt_power_sum_db") for item in results]
    fig, axes = plt.subplots(2, 1, figsize=(11.69, 8.27), sharex=True)
    axes[0].bar(lanes, loss, color="#4c78a8")
    axes[0].axhline(results[0].get("loss_limit_db", -7.5), color="red", linestyle="--", linewidth=1)
    axes[0].set_ylabel("IL at Nyquist (dB)")
    axes[0].grid(True, axis="y", linewidth=0.25)
    axes[1].bar(lanes, xt, color="#f58518")
    axes[1].axhline(results[0].get("xt_limit_db", -25.0), color="red", linestyle="--", linewidth=1)
    axes[1].set_ylabel("XT power-sum (dB)")
    axes[1].set_xlabel("Lane")
    axes[1].grid(True, axis="y", linewidth=0.25)
    fig.suptitle("Touchstone Sanity Check")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def path_text(value: Any) -> str:
    return str(value) if value else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a case PDF report from manifest/check summaries.")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--bench-workspace", default=None)
    args = parser.parse_args()

    case_dir = Path(args.case_dir).resolve()
    reports = case_dir / "reports"
    sim = case_dir / "simulation" / "hfss3dlayout"
    evidence_dir = case_dir / "spec_evidence"
    reports.mkdir(exist_ok=True)

    manifest = load_json(case_dir / "manifest.json")
    check_path = latest(list(reports.glob("channel_touchstone_check*.json")), prefer="padcapped")
    check = load_json(check_path)
    import_path = latest(list(sim.glob("*_import_summary.json")), prefer="padcapped")
    import_summary = load_json(import_path)
    solve_path = latest(list(sim.glob("*_solve_summary.json")), prefer="padcapped")
    solve_summary = load_json(solve_path)
    evidence = load_evidence(Path(manifest.get("artifacts", {}).get("spec_evidence", case_dir / "missing_spec_evidence.json")))
    evidence_snapshot = latest(list(evidence_dir.glob("*text_positions.png")))
    ads_summary_path = latest(list((case_dir / "ads").glob("*/reports/ads_snp_compliance_summary.json")))
    ads_summary = load_json(ads_summary_path)
    ads_bench = collect_ads_bench(Path(args.bench_workspace).resolve() if args.bench_workspace else None, case_dir)

    output = Path(args.output) if args.output else reports / f"{manifest.get('bundle_id', case_dir.name)}_final_report.pdf"

    board = manifest.get("board", {})
    routing = board.get("routing", {})
    dielectric = board.get("dielectric", {})
    pf = check.get("pass_fail", {})
    results = check.get("results", [])
    worst_loss = min((r.get("insertion_loss_db", 0.0) for r in results), default=0.0)
    worst_xt = max((r.get("xt_power_sum_db", -300.0) for r in results), default=-300.0)
    direct_builder = import_summary.get("selected_import", {}).get("direct_builder", {})
    created = direct_builder.get("created", {})
    touchstones = sorted(sim.glob("*.s*p"))

    status = "PASS" if pf.get("overall") else "FAIL / INCOMPLETE"
    lane_count = board.get("lanes", check.get("lane_count", "multi"))
    if ads_summary_path:
        ads_pf = ads_summary.get("pass_fail", {})
        ads_status = (
            "CREATED: ADS SnP handoff workspace/schematic exists; "
            f"deterministic overall={ads_pf.get('overall')}, crosstalk={ads_pf.get('crosstalk')}."
        )
    elif ads_bench.get("workspace"):
        eye_report = ads_bench.get("summary", {}).get("outputs", {}).get("eye_dataset_report", {})
        ads_status = (
            "CREATED: ADS strategy bench workspace exists; "
            f"eye density={eye_report.get('density_present')}, "
            f"BERContour={eye_report.get('ber_contour_valid')}."
        )
    else:
        ads_status = "PENDING: ADS workspace was not generated for this case."

    with PdfPages(output) as pdf:
        add_text_page(
            pdf,
            "SI/PI Harness Final Report",
            [
                f"Case: {manifest.get('bundle_id')}",
                f"Status: {status}",
                f"Generated from: {case_dir}",
                "",
                "Request summary:",
                "Spec-driven package/PCB channel generation with KiCad design, HFSS 3D Layout EM extraction,",
                "ADS compliance as the final gate.",
                "",
                "Current conclusion:",
                "PCB/project generation and PDF figure evidence capture are complete.",
                "HFSS import and port creation are complete for the pad-capped project.",
                f"Full x{lane_count} EM solve/export produced a Touchstone; required coverage is now 5x Nyquist.",
                "The generated channel is not compliant because the current dense routing fails the crosstalk check.",
                ads_status,
            ],
        )
        add_text_page(
            pdf,
            "Spec Evidence",
            [
                f"Document: {evidence.get('document')}",
                f"Source PDF: {evidence.get('source_pdf')}",
                f"Evidence file: {evidence.get('evidence_file')}",
                f"Package: {evidence.get('package')}",
                f"Bump map: {evidence.get('bump_map', {}).get('figure')} page {evidence.get('bump_map', {}).get('page')}",
                f"Bump map review: {evidence.get('bump_map', {}).get('reviewer_status')}",
                f"Exit order: {evidence.get('exit_order', {}).get('figure')} page {evidence.get('exit_order', {}).get('page')}",
                f"Exit order review: {evidence.get('exit_order', {}).get('reviewer_status')}",
                f"Pitch from note: {evidence.get('bump_map', {}).get('pitch_um_from_note')} um",
                "",
                "General harness rule:",
                "Every spec-driven task must extract text, tables, figures, pin/ball maps, equations, and page snapshots",
                "into spec_evidence before layout. Figure-derived maps remain unreviewed/proxy until visual evidence is stored.",
            ],
        )
        if evidence_snapshot:
            add_image_page(pdf, "PDF Figure Evidence Snapshot", evidence_snapshot, str(evidence_snapshot))
        add_text_page(
            pdf,
            "PCB Design",
            [
                f"Board size: {board.get('widthMm')} mm x {board.get('heightMm')} mm",
                f"Lanes: x{board.get('lanes')}, columns: {board.get('columns')}",
                f"Channel length target: {board.get('channelLengthMm')} mm",
                f"Trace width: {routing.get('trace_width_mm')} mm",
                f"Lane pitch: {routing.get('lane_pitch_mm')} mm",
                f"Stackup: F.Cu signal over In1.Cu reference, In2/B.Cu GND planes",
                f"Dielectric height: {dielectric.get('reference_height_mm')} mm, Er={dielectric.get('er')}",
                f"KiCad project: {manifest.get('artifacts', {}).get('kicad_project')}",
                f"KiCad PCB: {manifest.get('artifacts', {}).get('kicad_pcb')}",
            ],
        )
        add_board_layout_page(pdf, manifest)
        add_text_page(
            pdf,
            "HFSS 3D Layout",
            [
                f"Import summary: {import_path}",
                f"Import OK: {import_summary.get('ok')}",
                f"AEDT version: {import_summary.get('aedt_version')}",
                f"AEDT project: {import_summary.get('project')}",
                f"Selected import method: {import_summary.get('selected_import', {}).get('method')}",
                f"Port method: {import_summary.get('port_method')}",
                f"Ports created: {import_summary.get('selected_import', {}).get('aedt_save', {}).get('ports', {}).get('created_count')}",
                f"Reopen port count: {import_summary.get('selected_import', {}).get('aedt_save', {}).get('reopen_check', {}).get('port_count')}",
                f"Launch pad min/max mm: {created.get('launch_pad_size_min_mm')} / {created.get('launch_pad_size_max_mm')}",
                f"Nearest launch spacing: {created.get('nearest_launch_spacing_by_layer_mm')}",
                f"Solve summary: {solve_path}",
                f"Solve analyze result: {solve_summary.get('analyze_result')}",
                f"Touchstone exists: {solve_summary.get('touchstone_exists')}",
                f"Touchstone size: {solve_summary.get('touchstone_size')}",
                f"Touchstone files present: {[path.name for path in touchstones]}",
            ],
        )
        add_text_page(
            pdf,
            "Compliance Check",
            [
                f"Check summary: {check_path}",
                f"Port count: {check.get('port_count')}",
                f"Lane count: {check.get('lane_count')}",
                f"Nyquist: {check.get('nyquist_ghz')} GHz",
                f"Required stop: {check.get('required_stop_ghz')} GHz",
                f"Actual stop: {check.get('actual_stop_ghz')} GHz",
                f"Frequency coverage pass: {pf.get('frequency_range')}",
                f"Loss pass: {pf.get('loss')}",
                f"Crosstalk pass: {pf.get('crosstalk')}",
                f"Z0 proxy pass: {pf.get('z0_proxy')}",
                f"Overall: {pf.get('overall')}",
                f"Worst insertion-loss sample: {worst_loss:.3f} dB",
                f"Worst XT power-sum sample: {worst_xt:.3f} dB",
                "",
                "Blocking item:",
                "The current lane pitch and trace width leave insufficient spacing for the requested crosstalk target.",
                "HFSS through/loss behavior is good, but adjacent-lane NEXT dominates the multi-lane crosstalk power sum.",
                "Next design iteration must increase spacing, add shielding/ground returns, or use a different layer/escape strategy.",
            ],
        )
        add_check_plot_page(pdf, check)
        if ads_summary_path:
            add_text_page(
                pdf,
                "ADS Handoff",
                [
                    f"ADS summary: {ads_summary_path}",
                    f"Workspace: {ads_summary.get('workspace')}",
                    f"Touchstone in ADS data: {ads_summary.get('touchstone')}",
                    f"Schematic created: {ads_summary.get('ads_schematic', {}).get('created')}",
                    f"Schematic detail: {ads_summary.get('ads_schematic', {}).get('detail')}",
                    f"ADS deterministic overall: {ads_summary.get('pass_fail', {}).get('overall')}",
                    f"ADS deterministic crosstalk: {ads_summary.get('pass_fail', {}).get('crosstalk')}",
                    "",
                    "This ADS handoff is clean and uses the pad-capped HFSS S64P.",
                    "A full spec-specific ADS VTF/ChannelSim bench still needs the exact source/load/equation mapping for the selected spec.",
                ],
            )
        if ads_bench.get("workspace"):
            eye_report = ads_bench.get("summary", {}).get("outputs", {}).get("eye_dataset_report", {})
            commands = ads_bench.get("summary", {}).get("commands", {})
            channelsim = commands.get("channelsim_full_eye_netlist_smoke", {})
            vtf_summary = ads_bench.get("vtf_summary", {})
            add_text_page(
                pdf,
                "ADS Strategy Bench",
                [
                    f"Workspace: {ads_bench.get('workspace')}",
                    f"Bench summary: {ads_bench.get('summary_path')}",
                    f"VTF summary: {ads_bench.get('vtf_summary_path')}",
                    f"ChannelSim success: {channelsim.get('success')}",
                    f"ChannelSim BERContour open: {channelsim.get('ber_contour_open')}",
                    f"ChannelSim dataset: {channelsim.get('validated_dataset')}",
                    f"Eye density present: {eye_report.get('density_present')}",
                    f"Eye BERContour valid: {eye_report.get('ber_contour_valid')}",
                    f"Eye HeightAtBER: {eye_report.get('HeightAtBER')}",
                    f"Eye WidthAtBER: {eye_report.get('WidthAtBER')}",
                    f"VTF overall: {vtf_summary.get('overall')}",
                    "",
                    "Visual evidence:",
                    "The following pages include VTF loss, VTF crosstalk, and ADS ChannelSim eye density/BERContour/mask overlays.",
                ],
            )
            add_image_page(
                pdf,
                "ADS VTF Loss vs Frequency",
                Path(ads_bench["vtf_loss_png"]),
                "ADS loaded VTF loss versus frequency with spec reference overlay where available.",
            )
            add_image_page(
                pdf,
                "ADS VTF Crosstalk vs Frequency",
                Path(ads_bench["vtf_xt_png"]),
                "ADS crosstalk versus frequency with spec reference overlay where available.",
            )
            add_image_page(
                pdf,
                "ADS Eye Density, BERContour, and Mask",
                Path(ads_bench["eye_png"]),
                "ADS ChannelSim result: density, BERContour at target BER, and rectangular/spec mask overlay.",
            )

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
