from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements-pdf.txt"
MODULES = {
    "pypdf": "pypdf",
    "Pillow": "PIL",
    "matplotlib": "matplotlib",
    "PyMuPDF": "fitz",
}


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def status() -> dict[str, object]:
    modules = {
        package: {
            "module": module,
            "available": module_available(module),
        }
        for package, module in MODULES.items()
    }
    return {
        "python": sys.executable,
        "requirements": str(REQUIREMENTS),
        "modules": modules,
        "all_available": all(item["available"] for item in modules.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install/check Python dependencies for PDF text and figure evidence extraction.")
    parser.add_argument("--requirements", default=str(REQUIREMENTS))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    before = status()
    if args.check_only or before["all_available"]:
        print(json.dumps(before, indent=2))
        return 0 if before["all_available"] else 1

    requirements = Path(args.requirements).resolve()
    if not requirements.exists():
        raise FileNotFoundError(f"Requirements file not found: {requirements}")

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
    importlib.invalidate_caches()
    after = status()
    print(json.dumps(after, indent=2))
    return 0 if after["all_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
