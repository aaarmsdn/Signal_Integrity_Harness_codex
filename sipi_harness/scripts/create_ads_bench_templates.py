from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


LIB_NAME = "sipi_bench_lib"
FIXED_SNP_PORTS = {2, 4, 6, 8, 10, 12, 16}


def ads_string(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return value
    return f'"{value}"'


def set_param(instance: Any, name: str, value: str) -> bool:
    try:
        if name in instance.parameters:
            instance.parameters[name].value = value
            return True
        instance.parameters[name] = value
        return True
    except Exception:
        return False


def label_pin(design: Any, instance: Any, index: int, net_name: str, dx: float = 0.35, dy: float = 0.0) -> dict[str, Any]:
    terms = list(instance.get_inst_term_iter())
    if index >= len(terms):
        return {"net": net_name, "ok": False, "reason": f"pin index {index} >= term count {len(terms)}"}
    term = terms[index]
    net = design.find_or_add_net(net_name)
    try:
        term.net = net
    except Exception:
        pass
    pin = next(iter(terms[index].get_inst_pin_iter()))
    try:
        pin.net = net
    except Exception:
        pass
    x = float(pin.bbox.x1)
    y = float(pin.bbox.y1)
    visual_label = True
    try:
        wire = design.add_wire([(x, y), (x + dx, y + dy)])
        wire.add_wire_label(net_name)
    except Exception as exc:
        visual_label = False
        return {
            "net": net_name,
            "ok": True,
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
            "connection": "direct_term_and_pin_net",
            "visual_label": visual_label,
            "visual_label_error": str(exc),
        }
    return {
        "net": net_name,
        "ok": True,
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy,
        "connection": "direct_term_and_pin_net_plus_wire_label",
        "visual_label": visual_label,
    }


def label_term_number(
    design: Any,
    instance: Any,
    term_number: int,
    net_name: str,
    dx: float | None = 0.35,
    dy: float | None = 0.0,
) -> dict[str, Any]:
    """Label an ADS instance terminal by terminal number, not iteration order.

    Fixed ADS SnP symbols expose pins in a visual/geometry order that does not
    match the electrical port order. The `term_number` is the stable port/ref
    identifier used by the generated netlist.
    """
    for term in instance.get_inst_term_iter():
        try:
            current = int(term.term_number)
        except Exception:
            continue
        if current != term_number:
            continue
        net = design.find_or_add_net(net_name)
        try:
            term.net = net
        except Exception:
            pass
        pin = next(iter(term.get_inst_pin_iter()))
        try:
            pin.net = net
        except Exception:
            pass
        x = float(pin.bbox.x1)
        y = float(pin.bbox.y1)
        if dx is None or dy is None:
            coords = []
            for any_term in instance.get_inst_term_iter():
                try:
                    any_pin = next(iter(any_term.get_inst_pin_iter()))
                    coords.append((float(any_pin.bbox.x1), float(any_pin.bbox.y1)))
                except Exception:
                    continue
            if coords:
                min_x = min(px for px, _ in coords)
                max_x = max(px for px, _ in coords)
                min_y = min(py for _, py in coords)
                max_y = max(py for _, py in coords)
                eps = 1e-6
                if abs(y - min_y) < eps:
                    dx, dy = 0.0, -0.35
                elif abs(y - max_y) < eps:
                    dx, dy = 0.0, 0.35
                elif abs(x - min_x) < eps:
                    dx, dy = -0.35, 0.0
                elif abs(x - max_x) < eps:
                    dx, dy = 0.35, 0.0
                else:
                    dx, dy = 0.35, 0.0
            else:
                dx, dy = 0.35, 0.0
        visual_label = True
        try:
            wire = design.add_wire([(x, y), (x + dx, y + dy)])
            wire.add_wire_label(net_name)
        except Exception as exc:
            visual_label = False
            return {
                "net": net_name,
                "ok": True,
                "term_number": term_number,
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
                "connection": "direct_term_and_pin_net",
                "visual_label": visual_label,
                "visual_label_error": str(exc),
            }
        return {
            "net": net_name,
            "ok": True,
            "term_number": term_number,
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
            "connection": "direct_term_and_pin_net_plus_wire_label",
            "visual_label": visual_label,
        }
    return {"net": net_name, "ok": False, "term_number": term_number, "reason": "term_number not found"}


def save_netlist(design: Any, path: Path) -> dict[str, Any]:
    try:
        netlist = design.create_netlist()
        path.write_text(netlist, encoding="utf-8", errors="replace")
        return {"ok": True, "path": str(path), "bytes": len(netlist.encode("utf-8", errors="replace"))}
    except Exception as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


def create_sparam_check(dbu: Any, reports: Path, touchstone_name: str, port_count: int) -> dict[str, Any]:
    cell = "sparam_snp_check"
    design = dbu.create_schematic(f"{LIB_NAME}:{cell}:schematic")
    symbol_name = f"S{port_count}P" if port_count in FIXED_SNP_PORTS else "SnP"
    snp = design.add_instance(("ads_datacmps", symbol_name, "symbol"), (0, 0), name="SNP_CHANNEL")
    set_param(snp, "File", ads_string(touchstone_name))
    set_param(snp, "FileName", ads_string(touchstone_name))
    set_param(snp, "NumPorts", str(port_count))
    labels = []
    for port in range(1, port_count + 1):
        labels.append(label_term_number(design, snp, port, f"p{port}", dx=None, dy=None))
    labels.append(label_term_number(design, snp, port_count + 1, "gnd!", dx=None, dy=None))
    design.save_design()
    return {
        "cell": cell,
        "schematic": f"{LIB_NAME}:{cell}:schematic",
        "purpose": "Inspectable SnP/Touchstone check. The SnP file name is plain, no @ prefix.",
        "symbol": f"ads_datacmps:{symbol_name}",
        "labels": labels,
        "netlist": save_netlist(design, reports / f"{cell}.netlist.log"),
    }


def create_ac_check(dbu: Any, reports: Path) -> dict[str, Any]:
    cell = "ac_loaded_transfer_check"
    design = dbu.create_schematic(f"{LIB_NAME}:{cell}:schematic")
    ac = design.add_instance(("ads_simulation", "AC", "symbol"), (-4, 3), name="AC1")
    set_param(ac, "Start", "0.01 GHz")
    set_param(ac, "Stop", "6 GHz")
    set_param(ac, "Step", "0.05 GHz")
    src = design.add_instance(("ads_sources", "V_AC", "symbol"), (-4, 0), name="SRC")
    set_param(src, "Vac", "1 V")
    label_pin(design, src, 0, "src")
    label_pin(design, src, 1, "gnd!", dx=0.0, dy=-0.35)
    rsrc = design.add_instance(("ads_rflib", "R", "symbol"), (-2, 0), name="R_SRC")
    set_param(rsrc, "R", "30 Ohm")
    label_pin(design, rsrc, 0, "src")
    label_pin(design, rsrc, 1, "tx")
    c_tx = design.add_instance(("ads_rflib", "C", "symbol"), (-1, -1.0), name="C_TX")
    set_param(c_tx, "C", "0.2 pF")
    label_pin(design, c_tx, 0, "tx")
    label_pin(design, c_tx, 1, "gnd!")
    rrx = design.add_instance(("ads_rflib", "R", "symbol"), (2, 0), name="R_RX")
    set_param(rrx, "R", "50 Ohm")
    label_pin(design, rrx, 0, "rx")
    label_pin(design, rrx, 1, "gnd!")
    c_rx = design.add_instance(("ads_rflib", "C", "symbol"), (3.0, -1.0), name="C_RX")
    set_param(c_rx, "C", "0.2 pF")
    label_pin(design, c_rx, 0, "rx")
    label_pin(design, c_rx, 1, "gnd!")
    design.save_design()
    return {
        "cell": cell,
        "schematic": f"{LIB_NAME}:{cell}:schematic",
        "purpose": "AC loaded transfer check with explicit source resistance and shunt capacitance.",
        "netlist": save_netlist(design, reports / f"{cell}.netlist.log"),
    }


def create_eye_3lane_smoke(dbu: Any, reports: Path, touchstone_name: str) -> dict[str, Any]:
    cell = "channelsim_3lane_eye_smoke"
    design = dbu.create_schematic(f"{LIB_NAME}:{cell}:schematic")
    created: list[dict[str, Any]] = []

    def add(master: tuple[str, str, str], xy: tuple[float, float], name: str) -> Any | None:
        try:
            inst = design.add_instance(master, xy, name=name)
            created.append({"name": name, "master": ":".join(master), "ok": True})
            return inst
        except Exception as exc:
            created.append({"name": name, "master": ":".join(master), "ok": False, "error": str(exc)})
            return None

    chan = add(("ads_simulation", "ChannelSim", "symbol"), (-7, 4), "ChannelSim1")
    if chan:
        set_param(chan, "Mode", "Statistical")
        set_param(chan, "NumberOfBits", "1000")
        set_param(chan, "EnforcePassivity", "yes")
    tx = add(("ads_simulation", "Tx_SingleEnded", "symbol"), (-7, 0), "TX_VICTIM_L0")
    if tx:
        set_param(tx, "BitRate", "4 Gbps")
        set_param(tx, "Vhigh", "1.1 V")
        set_param(tx, "Vlow", "0 V")
        label_pin(design, tx, 0, "drv0")
    for lane, y in [(1, -1.4), (2, -2.8)]:
        xtlk = add(("ads_simulation", "Xtlk2_SingleEnded", "symbol"), (-7, y), f"XTLK2_L{lane}")
        if xtlk:
            set_param(xtlk, "PhaseToTxMode", "Fixed")
            set_param(xtlk, "PhaseToTx", "0.0")
            label_pin(design, xtlk, 0, f"drv{lane}")
    snp = add(("ads_datacmps", "S6P", "symbol"), (-1, -1.2), "SNP_3LANE")
    if snp:
        set_param(snp, "File", ads_string(touchstone_name))
        set_param(snp, "FileName", ads_string(touchstone_name))
        set_param(snp, "NumPorts", "6")
        for port, net in enumerate(["tx0", "rx0", "tx1", "rx1", "tx2", "rx2"], start=1):
            label_term_number(design, snp, port, net, dx=None, dy=None)
        label_term_number(design, snp, 7, "gnd!", dx=None, dy=None)
    eye = add(("ads_simulation", "Eye_Probe", "symbol"), (4, 0), "EYE_L0")
    if eye:
        set_param(eye, "Save_Contour", "yes")
        set_param(eye, "Save_WidthAtBER", "yes")
        set_param(eye, "Save_HeightAtBER", "yes")
        set_param(eye, "BERContour", "list(1e-27)")
        set_param(eye, "BERWidthHeight", "1e-27")
        set_param(eye, "ExtrapolateBER", "yes")
        label_pin(design, eye, 0, "rx0")
    for lane, y in [(0, 0), (1, -1.4), (2, -2.8)]:
        rsrc = add(("ads_rflib", "R", "symbol"), (-5, y), f"R_TX_SRC_L{lane}")
        if rsrc:
            set_param(rsrc, "R", "30 Ohm")
            label_pin(design, rsrc, 0, f"drv{lane}")
            label_pin(design, rsrc, 1, f"tx{lane}")
        crx = add(("ads_rflib", "C", "symbol"), (5.0, y - 0.45), f"C_RX_L{lane}")
        if crx:
            set_param(crx, "C", "0.2 pF")
            label_pin(design, crx, 0, f"rx{lane}")
            label_pin(design, crx, 1, "gnd!")
        rrx = add(("ads_rflib", "R", "symbol"), (6.0, y), f"R_RX_L{lane}")
        if rrx:
            set_param(rrx, "R", "50 Ohm")
            label_pin(design, rrx, 0, f"rx{lane}")
            label_pin(design, rrx, 1, "gnd!")

    design.save_design()
    return {
        "cell": cell,
        "schematic": f"{LIB_NAME}:{cell}:schematic",
        "purpose": "3-lane eye/ChannelSim smoke check: one victim Tx, two Xtlk2 aggressors, explicit RC loading.",
        "created_instances": created,
        "netlist": save_netlist(design, reports / f"{cell}.netlist.log"),
    }


def create_eye_full_check(dbu: Any, reports: Path, touchstone_name: str, port_count: int) -> dict[str, Any]:
    if port_count < 2 or port_count % 2:
        return {
            "cell": "channelsim_full_nlane_eye_check",
            "ok": False,
            "reason": f"port_count must be an even number >= 2, got {port_count}",
        }
    lane_count = port_count // 2
    cell = f"channelsim_full_{lane_count}lane_eye_check"
    design = dbu.create_schematic(f"{LIB_NAME}:{cell}:schematic")
    created: list[dict[str, Any]] = []

    def add(master: tuple[str, str, str], xy: tuple[float, float], name: str) -> Any | None:
        try:
            inst = design.add_instance(master, xy, name=name)
            created.append({"name": name, "master": ":".join(master), "ok": True})
            return inst
        except Exception as exc:
            created.append({"name": name, "master": ":".join(master), "ok": False, "error": str(exc)})
            return None

    chan = add(("ads_simulation", "ChannelSim", "symbol"), (-9, 4.0), "ChannelSim1")
    if chan:
        set_param(chan, "Mode", "Statistical")
        set_param(chan, "NumberOfBits", "1000")
        set_param(chan, "EnforcePassivity", "yes")
    tx = add(("ads_simulation", "Tx_SingleEnded", "symbol"), (-9, 0.0), "TX_VICTIM_L0")
    if tx:
        set_param(tx, "BitRate", "4 Gbps")
        set_param(tx, "Vhigh", "1.1 V")
        set_param(tx, "Vlow", "0 V")
        set_param(tx, "Mode", "Maximal Length LFSR")
        label_pin(design, tx, 0, "drv0")
    for lane in range(1, lane_count):
        y = -1.2 * lane
        xtlk = add(("ads_simulation", "Xtlk2_SingleEnded", "symbol"), (-9, y), f"XTLK2_L{lane}")
        if xtlk:
            set_param(xtlk, "PhaseToTxMode", "Fixed")
            set_param(xtlk, "PhaseToTx", "0.0")
            label_pin(design, xtlk, 0, f"drv{lane}")

    symbol_name = f"S{port_count}P" if port_count in FIXED_SNP_PORTS else "SnP"
    snp = add(("ads_datacmps", symbol_name, "symbol"), (-1.0, -0.6 * max(1, lane_count - 1)), "SNP_FULL")
    snp_labels: list[dict[str, Any]] = []
    if snp:
        set_param(snp, "File", ads_string(touchstone_name))
        set_param(snp, "FileName", ads_string(touchstone_name))
        set_param(snp, "NumPorts", str(port_count))
        for lane in range(lane_count):
            snp_labels.append(label_term_number(design, snp, 2 * lane + 1, f"tx{lane}", dx=None, dy=None))
            snp_labels.append(label_term_number(design, snp, 2 * lane + 2, f"rx{lane}", dx=None, dy=None))
        snp_labels.append(label_term_number(design, snp, port_count + 1, "gnd!", dx=None, dy=None))

    eye = add(("ads_simulation", "Eye_Probe", "symbol"), (5.0, 0.0), "EYE_L0")
    if eye:
        set_param(eye, "Save_Contour", "yes")
        set_param(eye, "Save_WidthAtBER", "yes")
        set_param(eye, "Save_HeightAtBER", "yes")
        set_param(eye, "BERContour", "list(1e-27)")
        set_param(eye, "BERWidthHeight", "1e-27")
        set_param(eye, "ExtrapolateBER", "yes")
        label_pin(design, eye, 0, "rx0")

    for lane in range(lane_count):
        y = -1.2 * lane
        rsrc = add(("ads_rflib", "R", "symbol"), (-6.8, y), f"R_TX_SRC_L{lane}")
        if rsrc:
            set_param(rsrc, "R", "30 Ohm")
            label_pin(design, rsrc, 0, f"drv{lane}")
            label_pin(design, rsrc, 1, f"tx{lane}")
        ctx = add(("ads_rflib", "C", "symbol"), (-5.2, y - 0.42), f"C_TX_L{lane}")
        if ctx:
            set_param(ctx, "C", "0.2 pF")
            label_pin(design, ctx, 0, f"tx{lane}")
            label_pin(design, ctx, 1, "gnd!")
        rrx = add(("ads_rflib", "R", "symbol"), (6.4, y), f"R_RX_L{lane}")
        if rrx:
            set_param(rrx, "R", "50 Ohm")
            label_pin(design, rrx, 0, f"rx{lane}")
            label_pin(design, rrx, 1, "gnd!")
        crx = add(("ads_rflib", "C", "symbol"), (7.6, y - 0.42), f"C_RX_L{lane}")
        if crx:
            set_param(crx, "C", "0.2 pF")
            label_pin(design, crx, 0, f"rx{lane}")
            label_pin(design, crx, 1, "gnd!")

    design.save_design()
    return {
        "cell": cell,
        "schematic": f"{LIB_NAME}:{cell}:schematic",
        "purpose": f"Full {lane_count}-lane ChannelSim bench: one victim Tx, {lane_count - 1} Xtlk2 aggressors, explicit RC loading, Eye probe BERContour.",
        "port_count": port_count,
        "lane_count": lane_count,
        "created_instances": created,
        "snp_labels": snp_labels,
        "netlist": save_netlist(design, reports / f"{cell}.netlist.log"),
    }


def write_bench_netlists(workspace: Path, touchstone_name: str, port_count: int) -> dict[str, str]:
    netlists = workspace / "netlists"
    netlists.mkdir(exist_ok=True)
    lane_count = max(1, port_count // 2)
    sparam = netlists / "sparam_inspection.ckt"
    sparam.write_text(
        "\n".join(
            [
                "; Generic SnP inspection netlist.",
                "; Copy the Touchstone into workspace data/ and use the plain filename.",
                '#uselib "ckt" , "SnP"',
                f'SnP:SNP_CHANNEL {" ".join(f"p{i}" for i in range(1, port_count + 1))} 0 File="{touchstone_name}" Type="touchstone" NumPorts={port_count} InterpMode="linear" ExtrapMode="constant"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    ac = netlists / "ac_loaded_transfer.ckt"
    ac.write_text(
        "\n".join(
            [
                "; Generic AC loaded transfer netlist.",
                "AC:AC1 Start=0.01 GHz Stop=6 GHz Step=0.05 GHz",
                "V_Source:SRC src 0 Type=\"V_AC\" Vac=polar(1,0) V Freq=freq",
                "R:R_SRC src tx R=30 Ohm",
                "C:C_TX tx 0 C=0.2 pF",
                "R:R_RX rx 0 R=50 Ohm",
                "C:C_RX rx 0 C=0.2 pF",
                "",
            ]
        ),
        encoding="utf-8",
    )
    eye = netlists / "channelsim_3lane_eye_smoke.ckt"
    eye.write_text(
        "\n".join(
            [
                "; Generic 3-lane ChannelSim eye smoke netlist.",
                'ChannelSim:ChannelSim1 Type="Statistical" ToleranceMode=1 EnforcePassivity=yes MaxImpulseLength=1000 NumberTimePtPerUI=32 StatusLevel=2 AntiAliasingWindow=1 ImpLFEOn=yes ImpCache=yes',
                '#load "python","TDM_Eye"',
                'ComponentWithNodes:EYE_L0 rx0 Type="ModelExtractor" Module="Eye" Save_Density=yes Save_Contour=yes Save_WidthAtBER=yes Save_HeightAtBER=yes BERWidthHeight=1e-27 BERContour=list(1e-27) ExtrapolateBER=yes DisableTransientOutput=yes',
                'TX:TX_VICTIM_L0 drv0 BitRate=4 Gbps Model="ADSTx" Vhigh=1.1 V Vlow=0 V RiseFallTime=100 psec Mode=0 RegisterLength=8 Encoder=0 TapInterval=1.0 EQMode=0',
                'XTLK:XTLK2_L1 drv1 Model="ADSXtlk" NewModel=yes SameSourceSettingAsTx=yes PhaseToTxMode=0 PhaseToTx=0.0 Vhigh=1.0 V Vlow=0.0 V RiseFallTime=100 psec',
                'XTLK:XTLK2_L2 drv2 Model="ADSXtlk" NewModel=yes SameSourceSettingAsTx=yes PhaseToTxMode=0 PhaseToTx=0.0 Vhigh=1.0 V Vlow=0.0 V RiseFallTime=100 psec',
                '#uselib "ckt" , "S6P"',
                f'S6P:SNP_3LANE tx0 rx0 tx1 rx1 tx2 rx2 0 File="{touchstone_name}" Type="touchstone" InterpMode="linear" InterpDom="" ExtrapMode="constant" Temp=27.0 CheckPassivity=0',
                "R:R_TX_SRC_L0 drv0 tx0 R=30 Ohm Noise=yes",
                "R:R_TX_SRC_L1 drv1 tx1 R=30 Ohm Noise=yes",
                "R:R_TX_SRC_L2 drv2 tx2 R=30 Ohm Noise=yes",
                "R:R_RX_L0 rx0 0 R=50 Ohm Noise=yes",
                "C:C_RX_L0 rx0 0 C=0.2 pF",
                "R:R_RX_L1 rx1 0 R=50 Ohm Noise=yes",
                "C:C_RX_L1 rx1 0 C=0.2 pF",
                "R:R_RX_L2 rx2 0 R=50 Ohm Noise=yes",
                "C:C_RX_L2 rx2 0 C=0.2 pF",
                "",
            ]
        ),
        encoding="utf-8",
    )
    full_eye = netlists / f"channelsim_full_{lane_count}lane_eye.ckt"
    full_lines = [
        f"; Full {lane_count}-lane ChannelSim eye/crosstalk bench.",
        "; This is the required topology pattern for an N-lane spec bench.",
        "; Replace source/load/model/equation values with reviewed strategy/spec evidence.",
        'ChannelSim:ChannelSim1 Type="Statistical" ToleranceMode=1 EnforcePassivity=yes MaxImpulseLength=1000 NumberTimePtPerUI=32 StatusLevel=2 AntiAliasingWindow=1 ImpLFEOn=yes ImpCache=yes',
        '#load "python","TDM_Eye"',
        'ComponentWithNodes:EYE_L0 rx0 Type="ModelExtractor" Module="Eye" Save_Density=yes Save_Contour=yes Save_WidthAtBER=yes Save_HeightAtBER=yes BERWidthHeight=1e-27 BERContour=list(1e-27) ExtrapolateBER=yes DisableTransientOutput=yes',
        'TX:TX_VICTIM_L0 drv0 BitRate=4 Gbps Model="ADSTx" Vhigh=1.1 V Vlow=0 V RiseFallTime=100 psec Mode=0 RegisterLength=8 Encoder=0 TapInterval=1.0 EQMode=0',
    ]
    for lane in range(1, lane_count):
        full_lines.append(
            f'XTLK:XTLK2_L{lane} drv{lane} Model="ADSXtlk" NewModel=yes SameSourceSettingAsTx=yes PhaseToTxMode=0 PhaseToTx=0.0 Vhigh=1.0 V Vlow=0.0 V RiseFallTime=100 psec'
        )
    fixed_symbol = f"S{port_count}P" if port_count in FIXED_SNP_PORTS else "SnP"
    full_lines.extend([f'#uselib "ckt" , "{fixed_symbol}"'])
    snp_nodes = []
    for lane in range(lane_count):
        snp_nodes.extend([f"tx{lane}", f"rx{lane}"])
    full_lines.append(
        (
            f'{fixed_symbol}:SNP_FULL {" ".join(snp_nodes)} 0 File="{touchstone_name}" '
            f'Type="touchstone" InterpMode="linear" InterpDom="" ExtrapMode="constant" Temp=27.0 CheckPassivity=0'
        )
    )
    for lane in range(lane_count):
        full_lines.append(f"R:R_TX_SRC_L{lane} drv{lane} tx{lane} R=30 Ohm Noise=yes")
        full_lines.append(f"C:C_TX_L{lane} tx{lane} 0 C=0.2 pF")
        full_lines.append(f"R:R_RX_L{lane} rx{lane} 0 R=50 Ohm Noise=yes")
        full_lines.append(f"C:C_RX_L{lane} rx{lane} 0 C=0.2 pF")
    full_lines.append("")
    full_eye.write_text("\n".join(full_lines), encoding="utf-8")
    return {
        "sparameter": str(sparam),
        "ac": str(ac),
        "channelsim_3lane_eye": str(eye),
        f"channelsim_full_{lane_count}lane_eye": str(full_eye),
    }


def promote_schematic_netlists(workspace: Path, port_count: int) -> dict[str, Any]:
    """Use ADS-DE exported schematic netlists as the runnable .ckt files.

    The hand-written netlists are useful as a fallback, but ADS ChannelSim
    emits important ModelExtractor defaults only when the schematic is netlisted
    by ADS itself. Running the schematic netlist keeps automation behavior
    aligned with what an engineer sees when pressing Simulate in ADS.
    """
    lane_count = max(1, port_count // 2)
    reports = workspace / "reports"
    netlists = workspace / "netlists"
    promoted: dict[str, Any] = {}
    pairs = {
        "sparameter": ("sparam_snp_check.netlist.log", "sparam_inspection.ckt"),
        "ac": ("ac_loaded_transfer_check.netlist.log", "ac_loaded_transfer.ckt"),
        "channelsim_3lane_eye": ("channelsim_3lane_eye_smoke.netlist.log", "channelsim_3lane_eye_smoke.ckt"),
        f"channelsim_full_{lane_count}lane_eye": (
            f"channelsim_full_{lane_count}lane_eye_check.netlist.log",
            f"channelsim_full_{lane_count}lane_eye.ckt",
        ),
    }
    for key, (src_name, dst_name) in pairs.items():
        src = reports / src_name
        dst = netlists / dst_name
        if not src.exists():
            promoted[key] = {"ok": False, "source": str(src), "reason": "schematic netlist log not found"}
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        if "Top Design" not in text or "Netlisted using" not in text:
            promoted[key] = {"ok": False, "source": str(src), "reason": "source does not look like an ADS schematic netlist"}
            continue
        dst.write_text(text, encoding="utf-8", errors="replace")
        promoted[key] = {"ok": True, "source": str(src), "destination": str(dst), "bytes": len(text.encode("utf-8", errors="replace"))}
    return promoted


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ADS bench workspace, schematics, and netlist checks.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--touchstone-name", default=None)
    parser.add_argument("--port-count", type=int, default=6)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    workspace_path = args.workspace.resolve()
    if args.port_count < 2 or args.port_count % 2:
        raise SystemExit("--port-count must be an even number >= 2")
    touchstone_name = args.touchstone_name or f"example_channel.s{args.port_count}p"
    if workspace_path.exists() and args.overwrite:
        shutil.rmtree(workspace_path)

    summary: dict[str, Any] = {
        "workspace": str(workspace_path),
        "library": LIB_NAME,
        "touchstone_filename_rule": "copy Touchstone into workspace data/ and use the plain filename; do not prefix @",
        "netlists": {},
        "schematics": [],
    }

    try:
        import keysight.ads.de as de
        from keysight.ads.de import db_uu as dbu

        if de.workspace_is_open():
            de.close_workspace()
        workspace = de.create_workspace(workspace_path)
        workspace.open()
        (workspace_path / "data").mkdir(exist_ok=True)
        reports = workspace_path / "reports"
        reports.mkdir(exist_ok=True)
        summary["netlists"] = write_bench_netlists(workspace_path, touchstone_name, args.port_count)
        lib_path = workspace_path / LIB_NAME
        de.create_new_library(LIB_NAME, lib_path)
        workspace.add_library(LIB_NAME, lib_path, de.LibraryMode.NON_SHARED)
        summary["schematics"].append(create_sparam_check(dbu, reports, touchstone_name, args.port_count))
        summary["schematics"].append(create_ac_check(dbu, reports))
        if args.port_count >= 6:
            summary["schematics"].append(create_eye_3lane_smoke(dbu, reports, touchstone_name))
        summary["schematics"].append(create_eye_full_check(dbu, reports, touchstone_name, args.port_count))
        summary["channelsim_schematic_status"] = "generated_and_netlisted_for_case_bench_use"
        workspace.close()
        summary["ads_de_workspace_created"] = True
        summary["promoted_schematic_netlists"] = promote_schematic_netlists(workspace_path, args.port_count)
    except Exception as exc:
        summary["ads_de_workspace_created"] = False
        summary["ads_de_error"] = str(exc)
        try:
            import keysight.ads.de as de

            if de.workspace_is_open():
                de.close_workspace()
        except Exception:
            pass
        workspace_path.mkdir(parents=True, exist_ok=True)
        (workspace_path / "data").mkdir(exist_ok=True)
        (workspace_path / "reports").mkdir(exist_ok=True)
        summary["netlists"] = write_bench_netlists(workspace_path, touchstone_name, args.port_count)

    reports = workspace_path / "reports"
    reports.mkdir(exist_ok=True)
    summary_path = reports / "ads_bench_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "summary": str(summary_path), "ads_de_workspace_created": summary.get("ads_de_workspace_created")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
