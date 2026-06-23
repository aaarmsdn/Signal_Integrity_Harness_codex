from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


DEFAULT_ADS_PYTHON = r"C:\Program Files\Keysight\ADS2026_Update2\tools\python\python.exe"
DEFAULT_HPEESOF_DIR = r"C:\Program Files\Keysight\ADS2026_Update2"


def ads_env(hpeesof_dir: str, clean_path: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    env["HPEESOF_DIR"] = hpeesof_dir
    env.pop("COMPL_DIR", None)
    env.pop("SIMARCH", None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    if clean_path:
        keep = []
        for item in env.get("PATH", "").split(os.pathsep):
            low = item.lower()
            if "keysight\\ads20" in low or "keysight/ads20" in low:
                continue
            keep.append(item)
        env["PATH"] = os.pathsep.join(keep)
    return env


def run_ads_script(
    script_path: str,
    script_args: list[str] | None = None,
    ads_python: str = DEFAULT_ADS_PYTHON,
    hpeesof_dir: str = DEFAULT_HPEESOF_DIR,
    out_dir: str | Path = ".",
    check: bool = True,
    timeout: int | None = None,
    clean_path: bool = False,
) -> subprocess.CompletedProcess:
    out = Path(out_dir).resolve()
    script = Path(script_path)
    if not script.is_absolute():
        script = out / script
    script = script.resolve()
    if not script.exists():
        raise FileNotFoundError(f"ADS build script not found: {script}")

    exe = Path(ads_python)
    if not exe.exists():
        raise FileNotFoundError(f"ADS python executable not found: {exe}")

    env = ads_env(hpeesof_dir, clean_path=clean_path)
    cmd = [str(exe), str(script), *(script_args or [])]
    print("ADS command:", *cmd, flush=True)
    print("HPEESOF_DIR:", env.get("HPEESOF_DIR"), flush=True)
    print("clean_path:", clean_path, flush=True)

    cp = subprocess.run(
        cmd,
        cwd=str(out),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    print("stdout:\n", cp.stdout, flush=True)
    print("stderr:\n", cp.stderr, flush=True)
    if check and cp.returncode != 0:
        raise RuntimeError(f"ADS build script failed (returncode={cp.returncode})")
    return cp


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ADS 2026 scripts with ADS Python.")
    parser.add_argument("script_path", nargs="?", default="ads_import_smoke.py")
    parser.add_argument("--ads-python", default=DEFAULT_ADS_PYTHON)
    parser.add_argument("--hpeesof-dir", default=DEFAULT_HPEESOF_DIR)
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--clean-path", action="store_true")
    parser.add_argument("--no-check", action="store_true")
    args, script_args = parser.parse_known_args()
    if script_args and script_args[0] == "--":
        script_args = script_args[1:]
    run_ads_script(
        script_path=args.script_path,
        script_args=script_args,
        ads_python=args.ads_python,
        hpeesof_dir=args.hpeesof_dir,
        out_dir=args.out_dir,
        check=not args.no_check,
        timeout=args.timeout,
        clean_path=args.clean_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
