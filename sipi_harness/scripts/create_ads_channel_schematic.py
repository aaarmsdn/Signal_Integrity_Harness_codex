from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADS = Path(r"C:\Program Files\Keysight\ADS2026_Update2")
DEFAULT_WORKSPACE = ROOT / "outputs" / "ads_channel_sim" / "microstrip_16gbps_wrk"
LIB = "ChannelSimulatorTutorial_lib"
CELL = "microstrip_16gbps"
VIEW = "schematic"


def build_ads_env(ads_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HPEESOF_DIR"] = str(ads_dir)
    env["COMPL_DIR"] = str(ads_dir)
    env["SIMARCH"] = "win32_64"
    env["DEINVOKE_NO_SPLASH"] = "1"
    env["ADS_NO_BACKGROUND"] = "on"
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env.pop("QT_PLUGIN_PATH", None)
    env.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    env["PATH"] = os.pathsep.join(
        [
            str(ads_dir / "bin"),
            str(ads_dir / "tools" / "python"),
            str(ads_dir / "adsptolemy" / "lib.win32_64"),
            env.get("PATH", ""),
        ]
    )
    return env


def ael_quote(path: Path | str) -> str:
    return json.dumps(str(path).replace("\\", "/"))


def make_ael(workspace: Path) -> str:
    netlist_name = "microstrip_16gbps_channel.ckt"
    return f"""
defun sipi_exit_on_error(code, class, op, line, col)
{{
  fputs(stderr, strcat("AEL error: ", class, " ", code, " at ", line, ":", col, "\\n"));
  de_exit();
  return TRUE;
}}

decl old_error = on_error(sipi_exit_on_error);
decl ok = de_open_workspace({ael_quote(workspace)});
decl context = de_create_new_schematic_view("{LIB}", "{CELL}", "{VIEW}");
decl windowH = de_show_context_in_new_window(context);

decl item;

item = de_init_item("ads_simulation:NetlistInclude:symbol");
de_set_item_id(item, "Include_Channel_Netlist");
de_set_item_parameters(item, list(prm("StdForm", "{netlist_name}")));
de_place_item(item, -3.5, 2.0);
de_free_item(item);

item = de_init_item("ads_simulation:ChannelSim:symbol");
de_set_item_id(item, "ChannelSim1");
de_place_item(item, -3.5, 0.2);
de_free_item(item);

item = de_init_item("ads_simulation:Tx_SingleEnded:symbol");
de_set_item_id(item, "Tx_SingleEnded1");
de_place_item(item, -3.5, -1.8);
de_free_item(item);

item = de_init_item("ads_datacmps:S2P:symbol");
de_set_item_id(item, "S2P_Channel");
de_set_item_parameters(item, list(prm("StdForm", "microstrip_50ohm_fr4_1p6_hfss3d.s2p")));
de_place_item(item, -0.5, -1.8);
de_free_item(item);

item = de_init_item("ads_simulation:Eye_Probe:symbol");
de_set_item_id(item, "Eye_Probe1");
de_place_item(item, 2.0, -0.7);
de_free_item(item);

item = de_init_item("ads_simulation:Term_SingleEnded:symbol");
de_set_item_id(item, "Term_SingleEnded1");
de_place_item(item, 2.0, -1.8);
de_free_item(item);

de_add_wire(-2.7, -1.8);
de_add_wire(-1.2, -1.8);
de_add_wire_label(-2.0, -1.8, "tx");

de_add_wire(0.2, -1.8);
de_add_wire(1.8, -1.8);
de_add_wire_label(1.0, -1.8, "rx");

de_add_wire(1.8, -1.8);
de_add_wire(1.8, -0.8);
de_add_wire_label(1.8, -1.1, "rx");

db_save_design_without_prompting(context);
de_close_workspace_without_prompting();
on_error(old_error);
de_exit();
"""


def register_workspace_cell(workspace_ads: Path) -> None:
    text = workspace_ads.read_text(encoding="utf-8", errors="replace")
    if f'<Cell Name="{LIB}:{CELL}" />' in text:
        return
    marker = '        <Folder Name="00_SIPI Microstrip 16Gbps">'
    insert = f'            <Cell Name="{LIB}:{CELL}" />\n'
    if marker not in text:
        return
    text = text.replace(marker, marker + "\n" + insert, 1)
    workspace_ads.write_text(text, encoding="utf-8")


def copy_filesweep_schematic_fallback(workspace: Path) -> Path:
    lib_dir = workspace / LIB
    src = lib_dir / "%File%Sweep"
    dst = lib_dir / CELL
    if not (src / "schematic" / "sch.oa").exists():
        raise FileNotFoundError(src / "schematic" / "sch.oa")
    dst.mkdir(parents=True, exist_ok=True)
    if (dst / "schematic").exists():
        shutil.rmtree(dst / "schematic")
    shutil.copytree(src / "schematic", dst / "schematic")
    shutil.copy2(src / "itemdef.atf", dst / "itemdef.atf")
    (dst / "itemdef.ael").write_text(
        'create_item("microstrip_16gbps","microstrip_16gbps","X",16,-1,NULL,"Component Parameters",NULL,"%43?global %;%d:%t %# %44?0%:%31?%C%:_net%c%;%;%e %b%r%8?%29?%:%30?%p %:%k%?[%1i]%;=%p %;%;%;%e%e","microstrip_16gbps","%t%b%r%38?%:\\n%39?all_parm%A%:%30?%s%:%k%?[%1i]%;=%s%;%;%;%e%e%;","SYM_0Port",3,NULL,0);\n',
        encoding="utf-8",
    )
    register_workspace_cell(workspace / "workspace.ads")
    return dst / "schematic"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ADS schematic cell for the SIPI 16 Gbps microstrip ChannelSim flow.")
    parser.add_argument("--ads-dir", type=Path, default=DEFAULT_ADS)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    args = parser.parse_args()

    ads = args.ads_dir / "bin" / "ads.exe"
    if not ads.exists():
        raise FileNotFoundError(ads)
    if not (args.workspace / "workspace.ads").exists():
        raise FileNotFoundError(args.workspace / "workspace.ads")

    # If the workspace is open in ADS GUI, non-visual AEL can wait on the OA lock.
    # Create a usable schematic cell immediately by cloning the ADS ChannelSim FileSweep cell.
    fallback_cell = copy_filesweep_schematic_fallback(args.workspace)

    ael_path = args.workspace / "create_microstrip_16gbps_schematic.ael"
    ael_path.write_text(make_ael(args.workspace), encoding="utf-8")
    log_path = args.workspace / "create_microstrip_16gbps_schematic.log"

    try:
        proc = subprocess.run(
        [str(ads), "-nw", "-m", str(ael_path)],
        cwd=args.workspace,
        env=build_ads_env(args.ads_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
            timeout=20,
        )
        returncode = proc.returncode
        stdout = proc.stdout
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = f"AEL creation timed out; retained FileSweep schematic clone fallback.\\n{exc}\\n"
    log_path.write_text(stdout, encoding="utf-8", errors="replace")
    register_workspace_cell(args.workspace / "workspace.ads")

    cell_dir = args.workspace / LIB / "microstrip_16gbps" / "schematic"
    summary = {
        "returncode": returncode,
        "workspace": str(args.workspace),
        "library": LIB,
        "cell": CELL,
        "view": VIEW,
        "cell_dir": str(cell_dir),
        "cell_exists": cell_dir.exists(),
        "fallback_clone": str(fallback_cell),
        "ael": str(ael_path),
        "log": str(log_path),
    }
    summary_path = args.workspace / "microstrip_16gbps_schematic_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if cell_dir.exists() else returncode


if __name__ == "__main__":
    raise SystemExit(main())
