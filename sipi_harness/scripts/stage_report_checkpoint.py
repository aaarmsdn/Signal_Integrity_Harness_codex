from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_STAGES = {"strategy", "pcb_package", "em_solve", "bench", "reports"}


def load_json(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate stage PDFs at a stage boundary and record the checkpoint in the case manifest."
    )
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(VALID_STAGES))
    parser.add_argument("--status", default="completed", choices=["completed", "proxy", "blocked", "failed"])
    parser.add_argument("--bench-workspace", default=None)
    parser.add_argument("--ads-workspace", default=None, help="Backward-compatible alias for --bench-workspace.")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    case_dir = Path(args.case_dir).resolve()
    if not case_dir.exists():
        raise FileNotFoundError(case_dir)

    report_script = Path(__file__).resolve().with_name("generate_stage_pdf_reports.py")
    cmd = [sys.executable, str(report_script), "--case-dir", str(case_dir)]
    workspace = args.bench_workspace or args.ads_workspace
    if workspace:
        cmd.extend(["--bench-workspace", str(Path(workspace).resolve())])

    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        sys.stdout.write(cp.stdout)
        sys.stderr.write(cp.stderr)
        raise RuntimeError(f"Stage report generation failed with return code {cp.returncode}")

    stage_manifest_path = case_dir / "reports" / "stage_report_manifest.json"
    report_manifest = load_json(stage_manifest_path)
    manifest_path = case_dir / "manifest.json"
    manifest = load_json(manifest_path)

    checkpoints = manifest.setdefault("stage_report_checkpoints", {})
    if not isinstance(checkpoints, dict):
        checkpoints = {}
        manifest["stage_report_checkpoints"] = checkpoints
    checkpoints[args.stage] = {
        "stage": args.stage,
        "status": args.status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage_report_manifest": str(stage_manifest_path),
        "reports": report_manifest,
        "bench_workspace": str(Path(workspace).resolve()) if workspace else None,
        "note": args.note,
        "run_mode_independent": True,
        "rule": "Generate and save stage PDFs whenever a stage boundary is crossed, regardless of run mode.",
    }
    manifest.setdefault("reports", {})["stage_report_manifest"] = str(stage_manifest_path)
    write_json(manifest_path, manifest)

    output = {
        "ok": True,
        "case_dir": str(case_dir),
        "stage": args.stage,
        "status": args.status,
        "stage_report_manifest": str(stage_manifest_path),
        "reports": report_manifest,
        "manifest": str(manifest_path),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
