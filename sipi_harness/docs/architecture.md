# Harness Architecture

This repository follows the same separation used by mature workflow harnesses:
generic workflow code is separated from case configuration, local tool profiles,
and examples.

## Layers

```text
configs/                 user-editable case defaults and tool profiles
docs/                    contracts, workflow, validation, checkpoints
examples/                runnable samples and application-specific references
scripts/                 generic entry points and tool adapters
scripts/lib/             reusable helper functions shared by adapters
outputs/                 generated case artifacts, ignored by Git
```

## What Belongs in Core

Core code may contain:

- Input schema checks.
- Path resolution.
- Manifest/report writing.
- Generic KiCad, AEDT, HFSS 3D Layout, ADS adapters.
- Generic port-intent handling.
- Generic Touchstone validation.
- Generic PDF evidence extraction.
- Deterministic routing utilities that take maps/rules as input.

Core code must not contain:

- A specific interface name as a default design target.
- A specific spec table, figure, or bump map as a hidden assumption.
- A fixed user machine path.
- A fixed project output directory outside the case config.
- Compliance thresholds that are not declared in config or strategy.

## What Belongs in Examples

Examples may contain:

- Concrete application scripts.
- Known-good sample inputs.
- Small expected outputs.
- Notes explaining why the example exists and what to change.

Examples must be labeled as examples. They are not the generic entry point.
If a case-specific script contains reusable logic, extract that logic into a
generic adapter or helper module and leave only example parameters in the
example folder.

## What Belongs in Config

Config files should hold:

- Case name and output root.
- Input paths.
- Stackup/material/routing assumptions.
- Tool versions and executable paths.
- Sweep settings.
- Validation limits and waiver policy.
- Report options.

Use `configs/default.yml` for portable defaults and copy it into a case folder
for real work. Keep local machine paths in an ignored local config or in
environment variables.

## Adapter Pattern

Tool adapters should accept explicit inputs and outputs:

```text
adapter(input files, config, output dir) -> summary JSON + artifacts
```

They should write actionable error messages and never claim success only from a
tool API return value. For example, HFSS solve success requires a non-empty
Touchstone with expected ports and frequency data, not just `analyze_setup()`.

## Example Promotion Rule

Promote code from `examples/` into `scripts/` only when all are true:

1. It accepts external config/input files.
2. It has no hidden spec/application constants.
3. It emits a summary JSON or manifest update.
4. It has a dry-run or smoke-test path.
5. It is documented in `docs/workflow.md` or a skill.

Otherwise keep it as an example.
