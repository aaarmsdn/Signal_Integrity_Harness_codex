from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from pyedb import Edb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix KiCad-imported HFSS 3D Layout AEDB stackup thicknesses.")
    parser.add_argument(
        "--source-aedb",
        required=True,
        help="Input AEDB path.",
    )
    parser.add_argument(
        "--dest-aedb",
        required=True,
        help="Output AEDB path.",
    )
    parser.add_argument(
        "--summary",
        required=True,
        help="Output summary JSON path.",
    )
    parser.add_argument("--version", default="2025.1")
    parser.add_argument("--dielectric-mm", type=float, default=1.6)
    parser.add_argument("--copper-um", type=float, default=35.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def copy_aedb(source: Path, dest: Path, overwrite: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if dest.exists():
        if not overwrite:
            raise FileExistsError(f"Destination AEDB exists. Pass --overwrite: {dest}")
        shutil.rmtree(dest)
    shutil.copytree(source, dest)


def layer_snapshot(edb: Edb) -> list[dict[str, object]]:
    rows = []
    for name, layer in edb.stackup.layers.items():
        rows.append(
            {
                "name": name,
                "type": getattr(layer, "type", None),
                "material": getattr(layer, "material", None),
                "fill_material": getattr(layer, "fill_material", None),
                "thickness": getattr(layer, "thickness", None),
                "lower_elevation": getattr(layer, "lower_elevation", None),
                "upper_elevation": getattr(layer, "upper_elevation", None),
            }
        )
    return rows


def primitive_counts(edb: Edb) -> dict[str, int | str]:
    try:
        primitives = list(edb.modeler.primitives)
        return {
            "total": len(primitives),
            "f.cu": sum(1 for primitive in primitives if getattr(primitive, "layer_name", "") == "f.cu"),
            "b.cu": sum(1 for primitive in primitives if getattr(primitive, "layer_name", "") == "b.cu"),
            "gnd": sum(1 for primitive in primitives if getattr(primitive, "net_name", "") == "GND"),
            "sig_50ohm": sum(1 for primitive in primitives if getattr(primitive, "net_name", "") == "SIG_50OHM"),
        }
    except Exception as exc:
        return {"error": str(exc)}


def ensure_ground_reference_plane(edb: Edb) -> bool:
    for primitive in list(edb.modeler.primitives):
        if getattr(primitive, "layer_name", "") == "b.cu" and getattr(primitive, "net_name", "") == "GND":
            return False

    plane = edb.modeler.create_rectangle(
        layer_name="b.cu",
        net_name="GND",
        lower_left_point=["1mm", "-39mm"],
        upper_right_point=["79mm", "-1mm"],
    )
    if not plane:
        raise RuntimeError("Failed to create B.Cu GND reference plane rectangle in AEDB.")
    return True


def reorder_stackup_layers(edb: Edb, ordered_names: list[str]) -> None:
    layer_collection = edb.core.Cell.LayerCollection()
    layer_collection.SetMode(edb.layout.layer_collection.GetMode())

    for name in ordered_names:
        layer = edb.stackup.layers[name]
        layer_collection.AddLayerBottom(layer._edb_object.Clone())

    for _, layer in edb.stackup.non_stackup_layers.items():
        layer_collection.AddLayerBottom(layer._edb_object.Clone())

    edb.stackup._edb_object = layer_collection
    edb.layout.layer_collection = layer_collection
    edb.stackup.update_layout()
    edb.stackup.refresh_layer_collection()


def write_stackup_control_xml(path: Path, dielectric_mm: float, copper_um: float) -> None:
    dielectric_m = dielectric_mm / 1000.0
    copper_m = copper_um * 1e-6
    xml = f'''<?xml version="1.0" ?>
<ns0:Control xmlns:ns0="http://www.ansys.com/control" schemaVersion="1.0">
    <Stackup schemaVersion="1.0">
        <Materials>
            <Material Name="air">
                <Permittivity><Double>1.0006</Double></Permittivity>
                <DielectricLossTangent><Double>0.0</Double></DielectricLossTangent>
            </Material>
            <Material Name="copper">
                <Conductivity><Double>58000000.0</Double></Conductivity>
            </Material>
            <Material Name="FR4_epoxy">
                <Permittivity><Double>4.3</Double></Permittivity>
                <DielectricLossTangent><Double>0.02</Double></DielectricLossTangent>
            </Material>
        </Materials>
        <Layers LengthUnit="meter">
            <Layer Material="FR4_epoxy" Name="f.mask" Thickness="0.0" Type="dielectric"/>
            <Layer Material="copper" Name="f.cu" Thickness="{copper_m}" Type="conductor" FillMaterial="FR4_epoxy" EtchFactor="0.0"/>
            <Layer Material="FR4_epoxy" Name="dielectric_1" Thickness="{dielectric_m}" Type="dielectric"/>
            <Layer Material="copper" Name="b.cu" Thickness="{copper_m}" Type="conductor" FillMaterial="FR4_epoxy" EtchFactor="0.0"/>
            <Layer Material="FR4_epoxy" Name="b.mask" Thickness="0.0" Type="dielectric"/>
            <Layer Name="Measures" Type="measure"/>
            <Layer Name="SIwave Regions" Type="siwavehfsssolverregions"/>
            <Layer Name="comp_+_top" Type="assembly"/>
            <Layer Name="f.silkscreen" Type="silkscreen"/>
            <Layer Name="f.paste" Type="solderpaste"/>
            <Layer Name="b.paste" Type="solderpaste"/>
            <Layer Name="b.silkscreen" Type="silkscreen"/>
            <Layer Name="Outline" Type="outline"/>
            <Layer Name="Rats" Type="airlines"/>
            <Layer Name="Errors" Type="errors"/>
            <Layer Name="Symbols" Type="symbol"/>
            <Layer Name="Postprocessing" Type="postprocessing"/>
        </Layers>
    </Stackup>
</ns0:Control>
'''
    path.write_text(xml, encoding="utf8")


def main() -> None:
    args = parse_args()
    source = Path(args.source_aedb)
    dest = Path(args.dest_aedb)
    copy_aedb(source, dest, args.overwrite)

    edb = Edb(edbpath=str(dest), isreadonly=False, version=args.version)
    try:
        before = layer_snapshot(edb)
        primitive_counts_before = primitive_counts(edb)
        control_xml = dest.with_name("stackup_fixed_control.xml")
        write_stackup_control_xml(control_xml, args.dielectric_mm, args.copper_um)
        edb.stackup.load(str(control_xml))
        reference_plane_added = ensure_ground_reference_plane(edb)
        edb.save()
        after = layer_snapshot(edb)
        primitive_counts_after = primitive_counts(edb)
    finally:
        edb.close()

    summary = {
        "ok": True,
        "source_aedb": str(source),
        "dest_aedb": str(dest),
        "aedt_version": args.version,
        "target_stackup": {
            "top_to_bottom_order": ["f.mask", "f.cu", "dielectric_1", "b.cu", "b.mask"],
            "f.cu": f"{args.copper_um}um copper",
            "dielectric_1": f"{args.dielectric_mm}mm FR4_epoxy",
            "b.cu": f"{args.copper_um}um copper",
        },
        "reference_plane": {
            "added": reference_plane_added,
            "layer": "b.cu",
            "net": "GND",
            "lower_left": ["1mm", "-39mm"],
            "upper_right": ["79mm", "-1mm"],
        },
        "primitive_counts_before": primitive_counts_before,
        "primitive_counts_after": primitive_counts_after,
        "before": before,
        "after": after,
    }
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
