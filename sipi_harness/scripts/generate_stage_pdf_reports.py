from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {}


def wrap(text: str, width: int = 105) -> list[str]:
    lines: list[str] = []
    for raw in str(text).splitlines() or [""]:
        current = raw
        while len(current) > width:
            split_at = current.rfind(" ", 0, width)
            if split_at < 40:
                split_at = width
            lines.append(current[:split_at])
            current = current[split_at:].lstrip()
        lines.append(current)
    return lines


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, title, fontsize=15, weight="bold", va="top")
    y = 0.90
    for line in lines:
        for wrapped in wrap(line):
            if y < 0.07:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                fig.text(0.08, 0.95, f"{title} (continued)", fontsize=15, weight="bold", va="top")
                y = 0.90
            fig.text(0.08, y, wrapped, fontsize=8.5, family="monospace", va="top")
            y -= 0.023
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_image_page(pdf: PdfPages, title: str, image_path: Path, caption: str) -> None:
    if not image_path.exists():
        return
    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    fig.suptitle(title, fontsize=15, fontweight="bold")
    ax.imshow(mpimg.imread(image_path))
    ax.axis("off")
    fig.text(0.06, 0.04, caption, fontsize=8, family="monospace")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_existing_image(pdf: PdfPages, title: str, image_value: Any, caption: str) -> None:
    if not image_value:
        return
    add_image_page(pdf, title, Path(str(image_value)), caption)


def latest(paths: list[Path]) -> Path | None:
    paths = [path for path in paths if path.exists()]
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def writable_pdf_path(path: Path) -> Path:
    if not path.exists():
        return path
    try:
        with path.open("ab"):
            pass
        return path
    except PermissionError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def summarize_artifacts(artifacts: dict[str, Any]) -> list[str]:
    lines = []
    for key, value in sorted(artifacts.items()):
        lines.append(f"{key}: {value}")
    return lines or ["No artifacts recorded."]


def write_strategy_report(case_dir: Path, reports: Path, manifest: dict[str, Any]) -> Path:
    artifacts = manifest.get("artifacts", {})
    output = writable_pdf_path(reports / "00_strategy_report.pdf")
    with PdfPages(output) as pdf:
        add_text_page(
            pdf,
            "Stage 0 - Strategy",
            [
                f"Case: {manifest.get('bundle_id', case_dir.name)}",
                f"Status: {manifest.get('status', 'unknown')}",
                "",
                "Required artifacts:",
                f"Pre-PCB wiki report: {artifacts.get('pre_pcb_wiki_strategy_report_pdf', 'missing')}",
                f"Design strategy YAML: {artifacts.get('design_strategy_yaml', 'missing')}",
                f"Spec evidence: {artifacts.get('spec_evidence', 'missing')}",
                "",
                "Gate:",
                "The PCB/package stage should not start until strategy PDF/YAML and spec evidence exist or the case is marked proxy.",
            ],
        )
        yaml_value = artifacts.get("design_strategy_yaml")
        yaml_path = Path(yaml_value) if yaml_value else None
        if yaml_path and yaml_path.is_file():
            add_text_page(pdf, "Design Strategy YAML", yaml_path.read_text(encoding="utf-8").splitlines())
    return output


def write_pcb_report(case_dir: Path, reports: Path, manifest: dict[str, Any]) -> Path:
    output = writable_pdf_path(reports / "01_pcb_package_report.pdf")
    board = manifest.get("board", {})
    geometry = manifest.get("geometry_review", {})
    artifacts = manifest.get("artifacts", {})
    with PdfPages(output) as pdf:
        add_text_page(
            pdf,
            "Stage 1 - PCB/Package Generation",
            [
                f"Board/package: {board.get('package_type', 'unknown')}",
                f"Board size: {board.get('widthMm')} mm x {board.get('heightMm')} mm",
                f"Channel length: {board.get('channelLengthMm')} mm",
                f"Lanes: {board.get('lanes')}",
                "",
                "Geometry gate:",
                *[f"{key}: {value}" for key, value in geometry.items()],
                "",
                "Artifacts:",
                *summarize_artifacts(artifacts),
            ],
        )
        preview = artifacts.get("kicad_layout_preview_png")
        if preview:
            add_image_page(
                pdf,
                "KiCad Layout Preview",
                Path(preview),
                "Top-down review image generated from the KiCad PCB/package file. Use this for human review; DRC and geometry gates remain authoritative.",
            )
    return output


def write_em_report(case_dir: Path, reports: Path, manifest: dict[str, Any]) -> Path:
    output = writable_pdf_path(reports / "02_em_solve_report.pdf")
    sim = case_dir / "simulation" / "hfss3dlayout"
    import_summary = load_json(latest(list(sim.glob("*_import_summary.json"))) or Path("__missing__"))
    solve_summary = load_json(latest(list(sim.glob("*_solve_summary.json"))) or Path("__missing__"))
    touchstones = sorted(str(path) for path in sim.glob("*.s*p"))
    with PdfPages(output) as pdf:
        add_text_page(
            pdf,
            "Stage 2 - PCB/Package EM Solve",
            [
                f"Import summary OK: {import_summary.get('ok', 'missing')}",
                f"Selected import method: {import_summary.get('selected_import', {}).get('method', 'missing')}",
                f"Port method: {import_summary.get('port_method', 'missing')}",
                f"AEDT project: {import_summary.get('project', 'missing')}",
                f"Solve result: {solve_summary.get('analyze_result', 'missing')}",
                f"Touchstone exists: {solve_summary.get('touchstone_exists', 'missing')}",
                "",
                "Touchstone files:",
                *(touchstones or ["missing"]),
            ],
        )
    return output


def write_bench_report(case_dir: Path, reports: Path, manifest: dict[str, Any], bench_workspace: Path | None) -> Path:
    output = writable_pdf_path(reports / "03_bench_report.pdf")
    bench_summaries = list(case_dir.glob("bench/**/reports/*.json"))
    bench_summaries.extend(case_dir.glob("ads/**/reports/*.json"))
    if bench_workspace:
        bench_summaries.extend(bench_workspace.glob("**/reports/*.json"))
    summary_path = latest(bench_summaries) if bench_summaries else None
    summary = load_json(summary_path or Path("__missing__"))
    workspace = bench_workspace
    if workspace is None:
        candidates = sorted((case_dir / "bench").glob("*_spec_wrk"))
        if candidates:
            workspace = candidates[-1]
    vtf = load_json((workspace / "ucie_x8_vtf_ac_metrics.json") if workspace else Path("__missing__"))
    eye = load_json((workspace / "ucie_x8_eye_metrics.json") if workspace else Path("__missing__"))
    vtf_manifest = load_json((workspace / "figures" / "vtf_curves" / "vtf_curves_manifest.json") if workspace else Path("__missing__"))
    eye_manifest = load_json((workspace / "figures" / "eye_diagrams" / "eye_diagrams_manifest.json") if workspace else Path("__missing__"))
    with PdfPages(output) as pdf:
        vtf_pf = vtf.get("pass_fail", {})
        eye_rows = eye.get("eye_metrics", []) if eye else []
        add_text_page(
            pdf,
            "Stage 3 - Bench",
            [
                f"Benchmark workspace: {workspace or 'not provided'}",
                f"Benchmark summary: {summary_path or 'missing'}",
                f"Pass/fail: {summary.get('pass_fail', 'missing')}",
                "",
                "Spec-derived bench summary:",
                f"VTF target frequency: {vtf.get('target_frequency_ghz', 'missing')} GHz",
                f"With-Rx-termination VTF overall: {vtf_pf.get('table_5_24_overall', 'missing')}",
                f"No-Rx-termination VTF overall: {vtf_pf.get('table_5_25_overall', 'missing')}",
                f"Eye/mask overall: {eye.get('overall_status', 'missing')}",
                f"Eye target BER: {eye.get('mask', {}).get('ber_target', 'missing')}",
                f"Eye height limit: {eye.get('mask', {}).get('height_limit_mv', 'missing')} mV",
                f"Eye width limit: {eye.get('mask', {}).get('width_limit_ui', 'missing')} UI",
                f"Eye lanes reported: {len([row for row in eye_rows if 'error' not in row])}",
                "",
                "Required visualization evidence:",
                "VTF/XT: report frequency-vs-loss and frequency-vs-crosstalk curves with spec limits overlaid.",
                "Eye: report ADS density, BERContour at target BER, and rectangular/spec mask overlay in the same figure.",
                "",
                "Rule:",
                "Benchmark benches must be generated from strategy/spec equations, not from copied example schematics.",
                "Touchstone, waveform, and stimulus files must use verified path syntax for the selected tool.",
                "Frequency-domain and transient-domain metrics must use the exact spec-defined equations and loading models.",
            ],
        )
        for condition, item in vtf_manifest.get("conditions", {}).items():
            add_existing_image(
                pdf,
                f"VTF Loss and Crosstalk vs Frequency - {condition}",
                item.get("overview_image"),
                "Measured VTF loss and XT power-sum curves. Dashed curves/lines are spec limits; vertical marker is Nyquist.",
            )
        for item in eye_manifest.get("results", [])[:8]:
            add_existing_image(
                pdf,
                f"ADS Eye Density, BERContour, and Mask - Lane {item.get('lane')}",
                item.get("image"),
                "ADS ChannelSim eye density with BERContour and rectangular/spec mask overlay at the target BER.",
            )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-stage PDF reports for a case.")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--bench-workspace", default=None)
    parser.add_argument("--ads-workspace", default=None, help="Backward-compatible alias for --bench-workspace.")
    args = parser.parse_args()

    case_dir = Path(args.case_dir).resolve()
    reports = case_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    manifest = load_json(case_dir / "manifest.json")
    workspace_arg = args.bench_workspace or args.ads_workspace
    bench_workspace = Path(workspace_arg).resolve() if workspace_arg else None

    outputs = {
        "strategy": str(write_strategy_report(case_dir, reports, manifest)),
        "pcb_package": str(write_pcb_report(case_dir, reports, manifest)),
        "em_solve": str(write_em_report(case_dir, reports, manifest)),
        "bench": str(write_bench_report(case_dir, reports, manifest, bench_workspace)),
    }
    (reports / "stage_report_manifest.json").write_text(json.dumps(outputs, indent=2), encoding="utf-8")
    print(json.dumps(outputs, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
