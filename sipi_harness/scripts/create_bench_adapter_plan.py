from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - dependency is normally installed.
    yaml = None


def load_strategy(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if yaml is None:
        raise RuntimeError("PyYAML is required to read design_strategy.yaml. Install pyyaml or pass JSON.")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Strategy file did not contain an object: {path}")
    return data


def validation_benches(strategy: dict[str, Any]) -> dict[str, Any]:
    root = strategy.get("design_strategy", strategy)
    benches = root.get("validation_benches", {})
    if not isinstance(benches, dict):
        return {}
    return benches


def build_adapter_plan(strategy: dict[str, Any]) -> dict[str, Any]:
    benches = validation_benches(strategy)
    blocked = benches.get("blocked_benches", [])
    if not isinstance(blocked, list):
        blocked = []
    plans = []
    for item in blocked:
        if not isinstance(item, dict):
            continue
        synth = item.get("adapter_synthesis", {})
        if not isinstance(synth, dict):
            synth = {}
        recommendation = synth.get("recommended_flow", {})
        plans.append(
            {
                "metric_name": item.get("metric_name"),
                "blocked_bench_id": item.get("id"),
                "implements_requirement": item.get("implements_requirement"),
                "contract_id": synth.get("contract_id", f"adapter_contract_{item.get('metric_name', 'metric')}"),
                "status": "adapter_plan_ready",
                "tool_family": recommendation.get("tool_family", "engineer_selected"),
                "bench_type": recommendation.get("bench_type", "custom_metric_adapter"),
                "required_inputs": synth.get("inputs", item.get("required_inputs", [])),
                "source_evidence_ids": synth.get("source_evidence_ids", item.get("source_requirement_evidence_ids", [])),
                "expected_outputs": synth.get(
                    "expected_outputs",
                    [
                        "machine-readable metric JSON",
                        "plot images when applicable",
                        "stage report section with source evidence IDs",
                    ],
                ),
                "implementation_notes": recommendation.get("implementation_notes", []),
                "minimum_acceptance": [
                    "Adapter reads source-derived requirement IDs from design_strategy.yaml.",
                    "Adapter refuses to invent pass/fail limits when tier-0 evidence is missing.",
                    "Adapter writes summary JSON and report-ready plots/tables.",
                    "Adapter records blocked status when required topology or model data is absent.",
                ],
            }
        )
    return {
        "schema_version": "bench_adapter_plan_v1",
        "status": "no_blocked_benches" if not plans else "adapter_generation_required",
        "adapter_count": len(plans),
        "plans": plans,
    }


def markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Bench Adapter Generation Plan",
        "",
        f"Status: `{plan.get('status')}`",
        f"Adapter count: {plan.get('adapter_count', 0)}",
        "",
    ]
    for item in plan.get("plans", []):
        lines.extend(
            [
                f"## {item.get('metric_name')}",
                "",
                f"- Contract: `{item.get('contract_id')}`",
                f"- Tool family: `{item.get('tool_family')}`",
                f"- Bench type: `{item.get('bench_type')}`",
                f"- Requirement: `{item.get('implements_requirement')}`",
                "- Required inputs:",
            ]
        )
        lines.extend(f"  - {value}" for value in item.get("required_inputs", []))
        lines.append("- Source evidence IDs:")
        lines.extend(f"  - `{value}`" for value in item.get("source_evidence_ids", []))
        lines.append("- Implementation notes:")
        lines.extend(f"  - {value}" for value in item.get("implementation_notes", []))
        lines.append("- Minimum acceptance:")
        lines.extend(f"  - {value}" for value in item.get("minimum_acceptance", []))
        lines.append("")
    return "\n".join(lines)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value).strip("_") or "adapter"


def adapter_script(metric_name: str) -> str:
    return f'''from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Case-local bench adapter skeleton for {metric_name}.")
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--touchstone", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = {{
        "schema_version": "bench_adapter_result_v1",
        "metric_name": contract.get("metric_name"),
        "contract_id": contract.get("contract_id"),
        "status": "blocked_adapter_skeleton_requires_metric_implementation",
        "reason": "The harness generated the adapter contract and runnable skeleton, but metric-specific equations/tool calls must be implemented before compliance can be claimed.",
        "source_evidence_ids": contract.get("source_evidence_ids", []),
        "required_inputs": contract.get("required_inputs", []),
        "provided_inputs": {{
            "touchstone": str(args.touchstone) if args.touchstone else None,
            "workspace": str(args.workspace) if args.workspace else None,
        }},
        "next_action": "Implement the tool calls/equations listed in implementation_notes, then change status to pass/fail with evidence-linked outputs.",
    }}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({{"result": str(args.out), "status": result["status"]}}, indent=2))


if __name__ == "__main__":
    main()
'''


def emit_skeletons(out_dir: Path, plan: dict[str, Any]) -> dict[str, Any]:
    adapters_dir = out_dir / "generated_adapters"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "bench_adapter_skeleton_manifest_v1", "adapters": []}
    readme_lines = [
        "# Generated Bench Adapter Skeletons",
        "",
        "These files are generated from `blocked_benches[].adapter_synthesis`.",
        "They are intentionally case-local. Use them to implement missing metric benches without inventing limits.",
        "",
    ]
    for item in plan.get("plans", []):
        metric = safe_name(str(item.get("metric_name", "metric")))
        contract_path = adapters_dir / f"{metric}_adapter_contract.json"
        script_path = adapters_dir / f"{metric}_adapter.py"
        result_path = adapters_dir / f"{metric}_adapter_result.json"
        contract = {
            "schema_version": "bench_adapter_contract_v1",
            **item,
        }
        contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
        script_path.write_text(adapter_script(metric), encoding="utf-8")
        manifest["adapters"].append(
            {
                "metric_name": item.get("metric_name"),
                "contract": str(contract_path),
                "script": str(script_path),
                "default_result": str(result_path),
                "status": "skeleton_generated_requires_metric_implementation",
            }
        )
        readme_lines.extend(
            [
                f"## {item.get('metric_name')}",
                "",
                f"- Contract: `{contract_path.name}`",
                f"- Script: `{script_path.name}`",
                f"- Tool family: `{item.get('tool_family')}`",
                f"- Bench type: `{item.get('bench_type')}`",
                "- Smoke command:",
                "",
                "```powershell",
                f"python {script_path.name} --contract {contract_path.name} --out {result_path.name}",
                "```",
                "",
            ]
        )
    manifest_path = adapters_dir / "adapter_manifest.json"
    readme_path = adapters_dir / "README.md"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    readme_path.write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return {"dir": str(adapters_dir), "manifest": str(manifest_path), "readme": str(readme_path), "count": len(manifest["adapters"])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a plan for missing bench adapters from design_strategy.yaml.")
    parser.add_argument("--strategy", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()

    strategy_path = args.strategy.resolve()
    out_dir = (args.out_dir or strategy_path.parent / "adapter_plan").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = build_adapter_plan(load_strategy(strategy_path))
    json_path = out_dir / "bench_adapter_plan.json"
    md_path = out_dir / "bench_adapter_plan.md"
    json_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown(plan) + "\n", encoding="utf-8")
    skeletons = emit_skeletons(out_dir, plan)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "markdown": str(md_path),
                "adapter_count": plan["adapter_count"],
                "skeletons": skeletons,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
