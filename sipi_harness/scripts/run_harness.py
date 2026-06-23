from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by user env
    raise SystemExit("PyYAML is required. Install with: python -m pip install pyyaml") from exc


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = Path(__file__).resolve().parents[1]

DESIGN_RUN_MODES = {
    "stage_review": {
        "label": "Stage Review Mode",
        "pause_policy": "pause_after_every_stage",
        "stage_repair_policy": "repair_within_stage_until_reviewable_or_blocked",
        "revision_policy": "engineer_review_between_stages",
        "description": "Pause after Strategy, PCB/Package, EM Solve, Bench, and Report for engineer review.",
    },
    "end_to_end_goal": {
        "label": "End-to-End Goal Mode",
        "pause_policy": "no_pause_unless_unresolved_blocker",
        "stage_repair_policy": "repair_within_stage_until_gate_passes_or_unresolved_blocker",
        "revision_policy": "auto_loop_from_final_report_to_strategy_if_metrics_fail",
        "description": "Run automatically through all five stages and loop for design revision when the final report shows failed metrics.",
    },
    "single_pass_design": {
        "label": "Single-Pass Design Mode",
        "pause_policy": "no_pause",
        "stage_repair_policy": "one_candidate_basic_validity_only",
        "revision_policy": "no_design_revision_loop_failures_reported_as_is",
        "description": "Run one candidate from Strategy to Report. Do not run design revision loops after failed metrics.",
    },
}

DESIGN_RUN_MODE_ALIASES = {
    "stage-review": "stage_review",
    "stage_review": "stage_review",
    "stage review": "stage_review",
    "staged_review": "stage_review",
    "end-to-end": "end_to_end_goal",
    "end_to_end": "end_to_end_goal",
    "end-to-end-goal": "end_to_end_goal",
    "end_to_end_goal": "end_to_end_goal",
    "goal": "end_to_end_goal",
    "single-pass": "single_pass_design",
    "single_pass": "single_pass_design",
    "single-pass-design": "single_pass_design",
    "single_pass_design": "single_pass_design",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or dry-run the SI/PI workflow harness.")
    parser.add_argument("--config", required=True, type=Path, help="Case YAML config.")
    parser.add_argument("--case-dir", type=Path, default=None, help="Override output case directory.")
    parser.add_argument("--stage", default="all", choices=["all", "strategy", "pcb_package", "em_solve", "bench", "ads_spec_check", "reports"])
    parser.add_argument(
        "--design-run-mode",
        choices=sorted(DESIGN_RUN_MODES),
        default=None,
        help="Override design run mode: stage_review, end_to_end_goal, or single_pass_design.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and write a plan without launching EDA tools.")
    parser.add_argument("--execute", action="store_true", help="Allow automated stages to launch tools where adapters exist.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def resolve_case_path(config_dir: Path, value: Any) -> Path | None:
    if value in (None, ""):
        return None
    text = str(value)
    if text.startswith("<repo>/"):
        return (REPO_ROOT / text[len("<repo>/") :]).resolve()
    path = Path(text)
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def sha256_file(path: Path) -> str | None:
    if not path or not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def check_required_keys(config: dict[str, Any], keys: list[str]) -> list[str]:
    missing = []
    for key in keys:
        cursor: Any = config
        for part in key.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                missing.append(key)
                break
            cursor = cursor[part]
    return missing


def read_port_intents(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    ports = data.get("ports")
    if not isinstance(ports, list) or not ports:
        raise ValueError("Port-intent JSON must contain a non-empty ports list.")
    required = {"name", "type", "net", "reference_net", "positive_layer", "negative_layer", "impedance_ohm", "role"}
    errors = []
    names = set()
    for index, port in enumerate(ports):
        missing = sorted(required - set(port))
        if missing:
            errors.append(f"port[{index}] missing {missing}")
        has_positive_point = "positive_x" in port and "positive_y" in port
        if not has_positive_point:
            errors.append(f"port[{index}] missing positive_x/positive_y")
        port_type = str(port.get("type", "edb_polygon_edge"))
        has_negative_point = "negative_x" in port and "negative_y" in port
        if port_type in {"circuit", "pin"} and not has_negative_point:
            errors.append(f"port[{index}] coordinate-port override missing negative_x/negative_y")
        if port_type in {"edb_polygon_edge", "edb_path_edge"} and has_negative_point:
            errors.append(
                f"port[{index}] edge-port intent should not include negative_x/negative_y; "
                "use reference_net/negative_layer and local reference edge selection instead"
            )
        name = port.get("name")
        if name in names:
            errors.append(f"duplicate port name: {name}")
        names.add(name)
    if errors:
        raise ValueError("; ".join(errors))
    return data


def read_bump_map(path: Path) -> dict[str, Any]:
    required = {"interface", "side", "pin", "row", "column", "x_mm", "y_mm", "net", "role", "layer"}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = sorted(required - fields)
        if missing:
            raise ValueError(f"Bump/pin map missing columns: {missing}")
        rows = list(reader)
    if not rows:
        raise ValueError("Bump/pin map is empty.")
    return {"row_count": len(rows), "columns": sorted(fields)}


def tool_version(command: list[str]) -> str | None:
    executable = shutil.which(command[0])
    if not executable:
        return None
    try:
        cp = subprocess.run([executable, *command[1:]], capture_output=True, text=True, timeout=10)
    except Exception:
        return executable
    line = (cp.stdout or cp.stderr or "").strip().splitlines()
    return line[0] if line else executable


def normalize_design_run_mode(value: Any) -> str | None:
    if value in (None, ""):
        return None
    key = str(value).strip().lower()
    key = key.removesuffix(" mode").replace("_mode", "")
    return DESIGN_RUN_MODE_ALIASES.get(key) or DESIGN_RUN_MODE_ALIASES.get(str(value).strip().lower())


def execution_mode_from_config(config: dict[str, Any], args: argparse.Namespace) -> str:
    if args.execute:
        return "execute"
    if args.dry_run:
        return "dry_run"
    harness = config.get("harness", {})
    explicit = harness.get("execution_mode")
    if explicit:
        return str(explicit)
    legacy = str(harness.get("run_mode", "dry_run"))
    return legacy if legacy in {"dry_run", "execute"} else "dry_run"


def design_mode_from_config(config: dict[str, Any], args: argparse.Namespace) -> str | None:
    if args.design_run_mode:
        return args.design_run_mode
    harness = config.get("harness", {})
    explicit = normalize_design_run_mode(harness.get("design_run_mode"))
    if explicit:
        return explicit
    legacy = normalize_design_run_mode(harness.get("run_mode"))
    if legacy:
        return legacy
    return None


def apply_run_mode_to_step(step: dict[str, Any], design_run_mode: str | None) -> None:
    mode = DESIGN_RUN_MODES.get(design_run_mode or "")
    if not mode:
        step["human_review"] = None
        step["pause_policy"] = "blocked_until_design_run_mode_selected"
        step["repair_policy"] = "blocked_until_design_run_mode_selected"
        step["revision_policy"] = "blocked_until_design_run_mode_selected"
        return
    step["pause_policy"] = mode["pause_policy"]
    step["repair_policy"] = mode["stage_repair_policy"]
    step["revision_policy"] = mode["revision_policy"]
    if design_run_mode == "stage_review":
        step["human_review"] = True
    else:
        step["human_review"] = False
    if design_run_mode != "stage_review":
        step.pop("review_gate_command", None)


def stage_plan(config: dict[str, Any], case_dir: Path, paths: dict[str, Path | None], selected_stage: str, design_run_mode: str | None) -> list[dict[str, Any]]:
    stages = config.get("workflow", {}).get("stages", {})
    if "bench" not in stages and "ads_spec_check" in stages:
        stages["bench"] = stages["ads_spec_check"]
    if selected_stage == "ads_spec_check":
        selected_stage = "bench"
    em = config.get("em_solver", {})
    ads = config.get("ads", {})
    all_steps = [
        {
            "name": "strategy",
            "purpose": "Build wiki-derived design strategy and pre-layout report.",
            "automated": stages.get("strategy", {}).get("automated", "semi"),
            "planned_command": (
                "npm run register:raw-sources; "
                "npm run report:wiki-strategy -- --case-dir <case-dir> "
                "--request-file <request.txt> --auto-ingest-sources"
            ),
            "review_gate_command": "review strategy/design_strategy.yaml, strategy report, and evidence gaps before PCB/package generation",
            "completion_criteria": [
                "strategy/design_strategy.yaml exists",
                "strategy PDF/JSON evidence summary exists",
                "raw/docling/spec-evidence hits are recorded, or explicit evidence gaps explain why they are absent",
                "raw source group names and README-only wiki folders are not used as design evidence",
                "content-level evidence is fused: docling/spec-evidence hit counts, reviewed typed cards, or explicit blockers",
                "spec metric coverage matrix maps required benches before routing",
                "missing/blocking spec values are recorded",
                "stage report checkpoint is generated with npm run report:checkpoint -- --stage strategy",
            ],
        },
        {
            "name": "pcb_package",
            "purpose": "Generate KiCad/package geometry, route records, geometry checks, and port intents.",
            "automated": stages.get("pcb_package", {}).get("automated", "semi"),
            "planned_command": "case-specific generator or KiCad/MCP adapter selected by strategy",
            "review_gate_command": "npm run prompt:stage-review -- --stage pcb --case-dir <case-dir>",
            "completion_criteria": [
                "complete KiCad/project or package layout bundle exists",
                "stackup and route records are written",
                "route_result records allow_diagonal=true or an engineer-approved exception",
                "high-speed routes preserve the strategy reference-plane/return-path contract",
                "local GND launch tabs are not counted as the channel reference plane",
                "routing repairs do not remove or fragment the assigned reference plane",
                "layout preview image exists and is shown for human review",
                "geometry gate passes or records a blocker/proxy status",
                "simulation/hfss3dlayout_port_intents.json exists",
                "stage report checkpoint is generated with npm run report:checkpoint -- --stage pcb_package",
            ],
        },
        {
            "name": "em_solve",
            "purpose": "Import board/package to HFSS 3D Layout and export verified Touchstone.",
            "automated": stages.get("em_solve", {}).get("automated", "semi"),
            "planned_command": (
                "npm run import:hfss3dlayout -- --port-method "
                f"{em.get('port_method', 'edb_polygon_edge')} ...; "
                "npm run solve:hfss3dlayout-touchstone -- ..."
            ),
            "review_gate_command": (
                "npm run prompt:stage-review -- --stage hfss --case-dir <case-dir> "
                f"--sweep-type {em.get('sweep', {}).get('sweep_type', 'Fast')} "
                f"--points {em.get('sweep', {}).get('smoke_points', 13)}"
            ),
            "completion_criteria": [
                "non-empty AEDB/AEDT project exists",
                "import summary records non-empty layers/nets/primitives",
                "reference-plane coverage gate passed before import/solve",
                "polygon-edge or approved port method preserves local signal/reference launch geometry",
                "ports persist after reopen and expected port count matches",
                "solve summary records sweep status",
                "non-empty Touchstone exists and passes port/frequency validation",
                "stage report checkpoint is generated with npm run report:checkpoint -- --stage em_solve",
            ],
        },
        {
            "name": "bench",
            "purpose": "Create frequency-domain and/or transient-domain benchmark benches and extract spec metrics.",
            "automated": stages.get("bench", {}).get("automated", "semi"),
            "planned_command": "ADS DE automation, circuit simulation, or post-processing selected by strategy",
            "review_gate_command": "npm run prompt:stage-review -- --stage ads --case-dir <case-dir> --touchstone <channel.sNp>",
            "completion_criteria": [
                "benchmark workspace/netlist/schematic or fallback script output exists",
                "Touchstone/waveform input path and port mapping are validated",
                "plots and dataset/report artifacts exist",
                "result is labeled compliance, proxy, or blocked with evidence",
                "stage report checkpoint is generated with npm run report:checkpoint -- --stage bench",
            ],
            "enabled": bool(ads.get("enabled", True)),
        },
        {
            "name": "reports",
            "purpose": "Generate stage reports and final manifest.",
            "automated": stages.get("reports", {}).get("automated", True),
            "planned_command": "npm run report:stages -- --case-dir <case-dir> [--ads-workspace <workspace>]",
            "review_gate_command": "review final report, manifest, evidence lineage, pass/fail/proxy labels, and next revision decision",
            "completion_criteria": [
                "stage PDFs exist",
                "manifest records artifact paths and status",
                "shareability/copyright notes are recorded",
            ],
        },
    ]
    selected = []
    for step in all_steps:
        if selected_stage != "all" and step["name"] != selected_stage:
            continue
        if not stages.get(step["name"], {}).get("enabled", True):
            step["enabled"] = False
        step.setdefault("enabled", True)
        apply_run_mode_to_step(step, design_run_mode)
        step["case_dir"] = str(case_dir)
        if paths.get("port_intents"):
            step["port_intents"] = str(paths["port_intents"])
        selected.append(step)
    return selected


def write_summary(case_dir: Path, manifest: dict[str, Any]) -> None:
    report_dir = case_dir / manifest["reports"]["output_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    summary = report_dir / "harness_run_summary.md"
    lines = [
        "# Harness Run Summary",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Case: `{manifest['case_name']}`",
        f"- Design run mode: `{manifest.get('design_run_mode')}`",
        f"- Execution mode: `{manifest.get('execution_mode')}`",
        f"- Generated: `{manifest['generated_at']}`",
        "",
        "## Input Checks",
    ]
    for check in manifest["checks"]:
        lines.append(f"- `{check['name']}`: {check['status']} - {check.get('detail', '')}")
    lines.extend(["", "## Planned Stages"])
    for step in manifest["stages"]:
        lines.append(
            f"- `{step['name']}`: enabled={step['enabled']}, automated={step['automated']}, "
            f"human_review={step['human_review']}, pause_policy={step.get('pause_policy')}"
        )
        lines.append(f"  - repair policy: {step.get('repair_policy')}")
        lines.append(f"  - revision policy: {step.get('revision_policy')}")
        if step.get("review_gate_command"):
            lines.append(f"  - review gate: `{step['review_gate_command']}`")
        for criterion in step.get("completion_criteria", []):
            lines.append(f"  - done when: {criterion}")
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {item}" for item in manifest["next_actions"])
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    config_dir = config_path.parent
    config = load_yaml(config_path)

    missing = check_required_keys(
        config,
        ["harness.case_name", "inputs.request", "inputs.stackup", "inputs.port_intents", "workflow.stages"],
    )
    if missing:
        raise ValueError(f"Config missing required keys: {missing}")

    case_name = str(config["harness"]["case_name"])
    output_root = resolve_case_path(config_dir, config.get("harness", {}).get("output_root", "outputs"))
    case_dir = args.case_dir.resolve() if args.case_dir else (output_root / case_name).resolve()
    reports_cfg = config.get("reports", {})
    report_dir_name = reports_cfg.get("output_dir", "reports")
    log_root = resolve_case_path(config_dir, config.get("harness", {}).get("log_root", "logs"))
    log_file = case_dir / "logs" / "harness.log"
    ensure_logging(log_file)

    execution_mode = execution_mode_from_config(config, args)
    design_run_mode = design_mode_from_config(config, args)
    if execution_mode != "dry_run":
        logging.warning("Execute mode is reserved for stage adapters. This entry point currently validates and plans.")

    input_cfg = config.get("inputs", {})
    paths = {key: resolve_case_path(config_dir, input_cfg.get(key)) for key in [
        "spec_pdf",
        "design_strategy",
        "stackup",
        "bump_map",
        "port_intents",
        "kicad_project",
        "kicad_board",
        "touchstone",
    ]}

    checks: list[dict[str, Any]] = []
    for key in ["stackup", "port_intents"]:
        path = paths[key]
        if not path or not path.exists():
            checks.append({"name": key, "status": "FAIL", "detail": f"missing required input: {path}"})
        else:
            checks.append({"name": key, "status": "PASS", "detail": str(path)})

    if paths.get("stackup") and paths["stackup"].exists():
        stackup_data = load_yaml(paths["stackup"])
        layer_count = len(stackup_data.get("layers", []))
        checks.append({"name": "stackup_schema", "status": "PASS" if layer_count else "FAIL", "detail": f"layers={layer_count}"})

    port_data = None
    if paths.get("port_intents") and paths["port_intents"].exists():
        try:
            port_data = read_port_intents(paths["port_intents"])
            expected = port_data.get("expected_port_count", len(port_data["ports"]))
            status = "PASS" if expected == len(port_data["ports"]) else "FAIL"
            checks.append({"name": "port_intents_schema", "status": status, "detail": f"ports={len(port_data['ports'])}, expected={expected}"})
        except Exception as exc:
            checks.append({"name": "port_intents_schema", "status": "FAIL", "detail": str(exc)})

    if paths.get("bump_map"):
        if not paths["bump_map"].exists():
            checks.append({"name": "bump_map", "status": "FAIL", "detail": f"missing optional configured file: {paths['bump_map']}"})
        else:
            try:
                info = read_bump_map(paths["bump_map"])
                checks.append({"name": "bump_map_schema", "status": "PASS", "detail": f"rows={info['row_count']}"})
            except Exception as exc:
                checks.append({"name": "bump_map_schema", "status": "FAIL", "detail": str(exc)})

    if paths.get("touchstone"):
        if not paths["touchstone"].exists():
            checks.append({"name": "touchstone", "status": "FAIL", "detail": f"configured Touchstone missing: {paths['touchstone']}"})
        elif paths["touchstone"].stat().st_size <= 0:
            checks.append({"name": "touchstone", "status": "FAIL", "detail": "Touchstone is empty"})
        else:
            checks.append({"name": "touchstone", "status": "PASS", "detail": str(paths["touchstone"])})

    tools = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "node": tool_version(["node", "--version"]),
        "kicad_cli": tool_version(["kicad-cli", "version"]),
        "git": tool_version(["git", "--version"]),
        "aedt_version_config": config.get("em_solver", {}).get("aedt_version"),
        "ads_min_version_config": config.get("ads", {}).get("min_version"),
    }

    if not design_run_mode:
        checks.append({
            "name": "design_run_mode",
            "status": "FAIL",
            "detail": "Select one of: stage_review, end_to_end_goal, single_pass_design.",
        })

    stages = stage_plan(config, case_dir, paths, args.stage, design_run_mode)
    failing_checks = [check for check in checks if check["status"] == "FAIL"]
    status = "BLOCKED" if failing_checks else "DRY_RUN_READY" if execution_mode == "dry_run" else "PLANNED"
    mode_contract = DESIGN_RUN_MODES.get(design_run_mode or "")

    manifest = {
        "schema": "sipi-harness.manifest.v1",
        "case_name": case_name,
        "status": status,
        "run_mode": design_run_mode,
        "design_run_mode": design_run_mode,
        "execution_mode": execution_mode,
        "run_mode_contract": mode_contract,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"path": str(config_path), "sha256": sha256_file(config_path)},
        "inputs": {key: {"path": str(path) if path else None, "sha256": sha256_file(path) if path else None} for key, path in paths.items()},
        "checks": checks,
        "stages": stages,
        "tools": tools,
        "reports": {"output_dir": report_dir_name},
        "logs": {"harness_log": str(log_file)},
        "next_actions": [
            "Review any FAIL or WARNING checks before running EDA tools.",
            "Approve strategy and spec evidence before geometry generation.",
            "For HFSS direct-AEDB fallback, run check:port-launch and require edb_polygon_edge ports on short endpoint launch edges with local reference copper.",
            "Only hand off to ADS after a verified non-empty Touchstone exists.",
        ],
    }

    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "logs").mkdir(parents=True, exist_ok=True)
    (case_dir / report_dir_name).mkdir(parents=True, exist_ok=True)
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_summary(case_dir, manifest)
    logging.info("Wrote manifest: %s", case_dir / "manifest.json")
    logging.info("Wrote summary: %s", case_dir / report_dir_name / "harness_run_summary.md")
    print(json.dumps({"status": status, "case_dir": str(case_dir), "manifest": str(case_dir / "manifest.json")}, indent=2))
    return 1 if failing_checks else 0


if __name__ == "__main__":
    raise SystemExit(main())
