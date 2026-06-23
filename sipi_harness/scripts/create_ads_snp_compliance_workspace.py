from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def load_json(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {}


def write_summary_files(
    workspace: Path,
    touchstone_dst: Path,
    check: dict[str, Any],
    schematic_status: dict[str, Any],
    bit_rate_gbps: float,
) -> dict[str, Any]:
    reports = workspace / "reports"
    reports.mkdir(exist_ok=True)
    pf = check.get("pass_fail", {})
    results = check.get("results", [])
    worst_xt = max(results, key=lambda row: row.get("xt_power_sum_db", -300.0)) if results else {}
    worst_il = min(results, key=lambda row: row.get("insertion_loss_db", 0.0)) if results else {}
    summary = {
        "workspace": str(workspace),
        "touchstone": str(touchstone_dst),
        "bit_rate_gbps": bit_rate_gbps,
        "nyquist_ghz": check.get("nyquist_ghz"),
        "required_stop_ghz": check.get("required_stop_ghz"),
        "actual_stop_ghz": check.get("actual_stop_ghz"),
        "pass_fail": pf,
        "worst_insertion_loss": worst_il,
        "worst_crosstalk": worst_xt,
        "ads_schematic": schematic_status,
        "notes": [
            "This workspace is a clean ADS handoff artifact for a generated SnP Touchstone.",
            "The deterministic pass/fail values come from the harness Touchstone postprocessor.",
            "Run an ADS AC/VTF or ChannelSim bench after mapping the applicable spec equations and required source/load models.",
        ],
    }
    (reports / "ads_snp_compliance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = [
        "# ADS SnP Compliance Handoff",
        "",
        f"- Workspace: `{workspace}`",
        f"- Touchstone: `{touchstone_dst.name}`",
        f"- Bit rate: {bit_rate_gbps:g} GT/s",
        f"- Nyquist: {check.get('nyquist_ghz')} GHz",
        f"- Required stop: {check.get('required_stop_ghz')} GHz",
        f"- Overall: {pf.get('overall')}",
        f"- Frequency coverage: {pf.get('frequency_range')}",
        f"- Loss: {pf.get('loss')}",
        f"- Crosstalk: {pf.get('crosstalk')}",
        f"- Z0 proxy: {pf.get('z0_proxy')}",
        "",
        "Worst rows:",
        f"- IL: lane {worst_il.get('lane')} = {worst_il.get('insertion_loss_db')} dB",
        f"- XT: lane {worst_xt.get('lane')} = {worst_xt.get('xt_power_sum_db')} dB",
        "",
        "ADS schematic:",
        f"- Created: {schematic_status.get('created')}",
        f"- Detail: {schematic_status.get('detail')}",
    ]
    (reports / "ads_snp_compliance_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return summary


def create_de_workspace(workspace: Path, touchstone_name: str, port_count: int) -> dict[str, Any]:
    try:
        import keysight.ads.de as de
        from keysight.ads.de import db_uu as db
    except Exception as exc:
        return {"created": False, "detail": f"ADS DE API import failed: {exc}"}

    lib_name = "sipi_compliance_lib"
    cell_name = "snp_compliance_handoff"
    try:
        if de.workspace_is_open():
            de.close_workspace()
        if workspace.exists():
            shutil.rmtree(workspace)
        ws = de.create_workspace(workspace)
        ws.open()
        lib_path = workspace / lib_name
        de.create_new_library(lib_name, lib_path)
        ws.add_library(lib_name, lib_path, de.LibraryMode.NON_SHARED)
        design = db.create_schematic(f"{lib_name}:{cell_name}:schematic")
        snp = design.add_instance(("ads_datacmps", "SnP", "symbol"), (0, 0), name="SnP_Channel")
        for key in ("File", "FileName", "TSfile"):
            try:
                snp.parameters[key].value = touchstone_name
            except Exception:
                pass
        try:
            snp.parameters["NumPorts"].value = str(port_count)
        except Exception:
            pass
        design.save_design()
        ws.close()
        return {
            "created": True,
            "detail": f"Created {lib_name}:{cell_name}:schematic with SnP_Channel",
            "library": lib_name,
            "cell": cell_name,
        }
    except Exception as exc:
        try:
            if de.workspace_is_open():
                de.close_workspace()
        except Exception:
            pass
        return {"created": False, "detail": f"ADS DE schematic generation failed: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a clean ADS workspace handoff for a generated SnP Touchstone.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--touchstone", type=Path, required=True)
    parser.add_argument("--check-json", type=Path, default=None)
    parser.add_argument("--bit-rate-gbps", type=float, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    args.workspace = args.workspace.resolve()
    args.touchstone = args.touchstone.resolve()
    if args.check_json:
        args.check_json = args.check_json.resolve()

    if not args.touchstone.exists():
        raise FileNotFoundError(args.touchstone)
    if args.workspace.exists() and args.overwrite:
        shutil.rmtree(args.workspace)
    args.workspace.mkdir(parents=True, exist_ok=True)
    data_dir = args.workspace / "data"
    data_dir.mkdir(exist_ok=True)
    touchstone_dst = data_dir / args.touchstone.name
    shutil.copy2(args.touchstone, touchstone_dst)

    check = load_json(args.check_json)
    port_count = int(check.get("port_count") or 0)
    schematic_status = create_de_workspace(args.workspace, touchstone_dst.name, port_count)
    if not touchstone_dst.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.touchstone, touchstone_dst)
    summary = write_summary_files(args.workspace, touchstone_dst, check, schematic_status, args.bit_rate_gbps)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
