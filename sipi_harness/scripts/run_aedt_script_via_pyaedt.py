import argparse
import json
import traceback
from pathlib import Path

from ansys.aedt.core import Desktop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AEDT script through PyAEDT Desktop gRPC.")
    parser.add_argument("script", type=Path)
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--non-graphical", action="store_true")
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    summary = {"ok": False, "script": str(args.script), "version": args.version}
    desktop = None
    try:
        desktop = Desktop(
            version=args.version,
            non_graphical=args.non_graphical,
            new_desktop=True,
            close_on_exit=False,
        )
        result = desktop.odesktop.RunScript(str(args.script.resolve()))
        summary["result"] = str(result)
        summary["ok"] = True
    except Exception as exc:
        summary["error"] = str(exc)
        summary["traceback"] = traceback.format_exc()
    finally:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if desktop:
            desktop.release_desktop(close_projects=False, close_desktop=False)


if __name__ == "__main__":
    main()
