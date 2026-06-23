# Adapting the Harness to a New Board or Package

Use this checklist when applying the harness to a new interface, package,
connector, PCB, interposer, or cable.

## 1. Create a Case Config

Copy:

```text
configs/default.yml -> outputs/<case>/config.yml
```

Edit only the copied config. Do not edit core scripts to add a case-specific
data rate, spec table, ball map, or file path.

## 2. Register Evidence

Add or reference:

- governing spec PDF or structured source
- user-approved references
- web research summaries
- stackup/material assumptions
- pin/ball/connector map

Do not put copyrighted PDFs or proprietary databases into Git unless rights are
explicit.

## 3. Build Strategy Before Layout

Before generating geometry, create or review:

- `strategy/design_strategy.yaml`
- strategy PDF/report
- required testbenches
- equations and limits
- loading models
- expected final reports

If the strategy cannot name the final ADS/circuit bench, the layout stage is not
ready.

## 4. Generate or Import Geometry

Use a case generator, KiCad/MCP, or an existing board database. The output must
include:

- board/package artifact
- stackup
- route records
- geometry checks
- `simulation/hfss3dlayout_port_intents.json`
- manifest update

## 5. Handoff to HFSS 3D Layout

Preferred flow:

1. Try native ODB++/IPC-2581 import.
2. Validate non-empty AEDB.
3. If native import is empty or unstable, use direct KiCad-to-AEDB fallback.
4. Run `check:port-launch` and verify every port has usable signal launch and
   local reference geometry. Empty launch/reference geometry is a blocker.
5. Use AEDB polygon-edge circuit ports by default:
   `--port-method edb_polygon_edge --edge-port-type Gap`. `edb_path_edge`,
   coordinate `circuit` ports, and `pin` ports are explicit override/debug
   paths only. Do not use them as automatic retries after polygon-edge failure.
6. Reopen AEDT and verify port count/order.
7. Solve and export Touchstone.
8. Validate Touchstone dimensions before ADS.

## 6. Build Spec Verification Bench

Use the strategy to create ADS or equivalent benches. Validate:

- schematic connectivity
- Touchstone filename/path syntax
- source/load/capacitance/termination model
- dataset and DDS paths
- metric extraction formulas

## 7. Report

Generate per-stage reports:

- strategy report
- PCB/package report
- EM solve report
- Bench/spec check report

Mark results as `PASS`, `FAIL`, `BLOCKED`, or `PROXY`. Do not turn a proxy
result into compliance without a waiver and human sign-off.
