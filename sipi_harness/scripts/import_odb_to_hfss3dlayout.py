from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a KiCad ODB++ export into Ansys HFSS 3D Layout through PyAEDT."
    )
    parser.add_argument(
        "--odb",
        required=True,
        help="Full path to the ODB++ zip exported from KiCad.",
    )
    parser.add_argument(
        "--aedb",
        required=True,
        help="Output AEDB folder to create for HFSS 3D Layout.",
    )
    parser.add_argument("--version", default="2025.1", help="AEDT version, for example 2025.1 or 2024.2.")
    parser.add_argument("--non-graphical", action="store_true", help="Launch AEDT without GUI.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing AEDB folder.")
    parser.add_argument(
        "--summary",
        required=True,
        help="JSON summary path.",
    )
    parser.add_argument(
        "--release-desktop",
        action="store_true",
        help="Release the AEDT desktop session after import. This does not close unrelated existing AEDT sessions.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    odb = Path(args.odb)
    aedb = Path(args.aedb)
    summary_path = Path(args.summary)

    if not odb.exists():
        raise FileNotFoundError(f"ODB++ file not found: {odb}")
    if aedb.exists():
        if not args.overwrite:
            raise FileExistsError(f"AEDB already exists. Pass --overwrite to replace it: {aedb}")
        shutil.rmtree(aedb)

    import_input = odb
    extracted_from_zip = False
    if odb.suffix.lower() == ".zip":
        import_input = odb.with_suffix("")
        if import_input.exists():
            shutil.rmtree(import_input)
        import_input.mkdir(parents=True)
        with zipfile.ZipFile(odb, "r") as archive:
            archive.extractall(import_input)
        extracted_from_zip = True

    from ansys.aedt.core import Hfss3dLayout

    h3d = Hfss3dLayout(
        project=None,
        version=args.version,
        non_graphical=args.non_graphical,
        new_desktop=True,
        close_on_exit=False,
    )

    ok = h3d.import_odb(
        input_file=str(import_input),
        output_dir=str(aedb),
        control_file=None,
        set_as_active=True,
        close_active_project=False,
    )

    if not ok:
        raise RuntimeError(f"HFSS 3D Layout ODB++ import failed: {odb}")

    summary = {
        "ok": True,
        "method": "ansys.aedt.core.hfss3dlayout.Hfss3dLayout.import_odb",
        "odb": str(odb),
        "import_input": str(import_input),
        "extracted_from_zip": extracted_from_zip,
        "aedb": str(aedb),
        "aedt_version": args.version,
        "non_graphical": args.non_graphical,
        "project_file": getattr(h3d, "project_file", None),
        "design_name": getattr(h3d, "design_name", None),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))
    if args.release_desktop:
        h3d.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    main()
