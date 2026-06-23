from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[1]
CONFIG = HARNESS_ROOT / "examples" / "sample_case" / "config.yml"
OUT = HARNESS_ROOT / "examples" / "sample_case" / "_smoke_output"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    cmd = [
        sys.executable,
        str(HARNESS_ROOT / "scripts" / "run_harness.py"),
        "--config",
        str(CONFIG),
        "--case-dir",
        str(OUT),
        "--dry-run",
    ]
    cp = subprocess.run(cmd, cwd=str(HARNESS_ROOT), capture_output=True, text=True)
    if cp.returncode != 0:
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        return cp.returncode
    manifest_path = OUT / "manifest.json"
    summary_path = OUT / "reports" / "harness_run_summary.md"
    if not manifest_path.exists() or not summary_path.exists():
        print("Sample smoke test did not create expected manifest/report.", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "DRY_RUN_READY":
        print(f"Unexpected sample status: {manifest.get('status')}", file=sys.stderr)
        return 3
    port_check = [check for check in manifest.get("checks", []) if check.get("name") == "port_intents_schema"]
    if not port_check or "ports=4" not in port_check[0].get("detail", ""):
        print("Port-intent schema check did not report 4 ports.", file=sys.stderr)
        return 4
    print(f"Sample smoke test passed: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
