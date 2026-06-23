from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile


def set_param(instance, name: str, value: str) -> None:
    try:
        if name in instance.parameters:
            instance.parameters[name] = value
    except Exception:
        pass


def label_first_pin(design, instance, net_name: str) -> None:
    term = next(iter(instance.get_inst_term_iter()))
    pin = next(iter(term.get_inst_pin_iter()))
    x = float(pin.bbox.x1)
    y = float(pin.bbox.y1)
    wire = design.add_wire([(x, y), (x + 0.35, y)])
    wire.add_wire_label(net_name)


def main() -> int:
    import keysight.ads.de as de
    from keysight.ads.de import db_uu as dbu

    workspace_path = Path(tempfile.gettempdir()) / "ads_ac_probe_wrk"
    shutil.rmtree(workspace_path, ignore_errors=True)
    workspace = de.create_workspace(workspace_path)
    workspace.open()
    de.create_new_library("probe_lib", workspace_path / "probe_lib")
    workspace.add_library("probe_lib", workspace_path / "probe_lib", de.LibraryMode.NON_SHARED)
    design = dbu.create_schematic("probe_lib:ac_probe:schematic")
    ac = design.add_instance(("ads_simulation", "AC", "symbol"), (0, 4), name="AC1")
    set_param(ac, "Start", "0.1 GHz")
    set_param(ac, "Stop", "16 GHz")
    set_param(ac, "Step", "0.1 GHz")
    src = design.add_instance(("ads_sources", "V_AC", "symbol"), (0, 0), name="SRC")
    set_param(src, "Vac", "1 V")
    label_first_pin(design, src, "tx0")
    gnd = design.add_instance(("ads_rflib", "GROUND", "symbol"), (0, -1), name="GND")
    term = design.add_instance(("ads_simulation", "Term", "symbol"), (2, 0), name="P1")
    set_param(term, "Num", "1")
    set_param(term, "Z", "50 Ohm")
    label_first_pin(design, term, "rx0")
    design.save_design()
    netlist = design.create_netlist()
    print(json.dumps({"workspace": str(workspace_path), "netlist": netlist}, indent=2))
    workspace.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
