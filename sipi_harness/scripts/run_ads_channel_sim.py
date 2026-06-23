from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADS = Path(r"C:\Program Files\Keysight\ADS2026_Update2")
DEFAULT_WORKSPACE = ROOT / "outputs" / "ads_channel_sim" / "microstrip_4gbps_wrk"


def build_ads_env(ads_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HPEESOF_DIR"] = str(ads_dir)
    env["COMPL_DIR"] = str(ads_dir)
    env["SIMARCH"] = "win32_64"
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PATH"] = os.pathsep.join(
        [
            str(ads_dir / "bin"),
            str(ads_dir / "tools" / "python"),
            str(ads_dir / "adsptolemy" / "lib.win32_64"),
            env.get("PATH", ""),
        ]
    )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ADS hpeesofsim for the SIPI 4 Gbps ChannelSim netlist.")
    parser.add_argument("--ads-dir", type=Path, default=DEFAULT_ADS)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--netlist", default="microstrip_4gbps_channel.ckt")
    args = parser.parse_args()

    sim = args.ads_dir / "bin" / "hpeesofsim.exe"
    netlist = args.workspace / args.netlist
    if not sim.exists():
        raise FileNotFoundError(sim)
    if not netlist.exists():
        raise FileNotFoundError(netlist)

    dataset_name = "microstrip_4gbps_channel"
    proc = subprocess.run(
        [str(sim), f"--dataset-name={dataset_name}", f".\\{netlist.name}"],
        cwd=args.workspace,
        env=build_ads_env(args.ads_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    log_path = args.workspace / "microstrip_4gbps_channel_hpeesofsim.log"
    log_path.write_text(proc.stdout, encoding="utf-8", errors="replace")

    ds_candidates = [
        args.workspace / f"{dataset_name}.ds",
        args.workspace / "data" / f"{dataset_name}.ds",
        args.workspace / "microstrip_4gbps.ds",
    ]
    ds_path = next((candidate for candidate in ds_candidates if candidate.exists()), ds_candidates[0])
    summary = {
        "returncode": proc.returncode,
        "simulation_ok": proc.returncode == 0,
        "workspace": str(args.workspace),
        "netlist": str(netlist),
        "log": str(log_path),
        "dataset_name": dataset_name,
        "dataset_exists": ds_path.exists(),
        "dataset": str(ds_path),
        "dataset_candidates": [str(candidate) for candidate in ds_candidates],
    }
    if proc.returncode != 0 and "valid\n    Channelsim license is not available" in proc.stdout:
        summary["blocker"] = "ADS ChannelSim license is not available in the current license path."
    summary_path = args.workspace / "microstrip_4gbps_channel_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
