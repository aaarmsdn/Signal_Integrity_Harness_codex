from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyedb import Edb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify an HFSS 3D Layout AEDB imported from KiCad ODB++.")
    parser.add_argument(
        "--aedb",
        required=True,
        help="AEDB path to verify.",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help="Output summary JSON path.",
    )
    parser.add_argument("--version", default="2025.1")
    return parser.parse_args()


def names_from_mapping_or_list(value) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    return sorted(str(item) for item in value)


def main() -> None:
    args = parse_args()
    aedb = Path(args.aedb)
    if not aedb.exists():
        raise FileNotFoundError(aedb)

    edb = Edb(edbpath=str(aedb), isreadonly=True, version=args.version)
    try:
        nets = names_from_mapping_or_list(edb.nets.nets)
        layers = names_from_mapping_or_list(edb.stackup.layers)
        components = names_from_mapping_or_list(edb.components.components)
        summary = {
            "ok": True,
            "aedb": str(aedb),
            "version": args.version,
            "net_count": len(nets),
            "nets": nets,
            "layer_count": len(layers),
            "layers": layers,
            "component_count": len(components),
            "components": components,
            "required_nets_present": all(net in nets for net in ["SIG_50OHM", "GND"]),
            "required_layers_present": all(layer in layers for layer in ["f.cu", "b.cu"]),
        }
    finally:
        edb.close()

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
