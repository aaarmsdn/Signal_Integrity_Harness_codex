---
name: ads-de-automation
description: Use Keysight ADS Design Environment Python API to create and validate ADS workspaces, schematics, ChannelSim benches, SnP/Touchstone based SI/PI compliance checks, DDS/dataset reports, and ADS automation for spec-driven harness flows.
---

# Keysight ADS Design Environment Automation

Use this skill when a task needs ADS workspace, schematic, ChannelSim, SnP/Touchstone, DDS, dataset, or spec-compliance automation.

## Runtime

Require ADS 2025 Update 2 or newer. Do not run this harness ADS automation on
older ADS versions unless a task-specific compatibility patch is written and
validated.

Prefer ADS Python, not system Python. The known-good default for this harness is
`C:\Program Files\Keysight\ADS2026_Update2\tools\python\python.exe`:

```powershell
$env:HPEESOF_DIR='C:\Program Files\Keysight\ADS2026_Update2'
$env:COMPL_DIR=$env:HPEESOF_DIR
$env:SIMARCH='win32_64'
$env:PATH="$env:HPEESOF_DIR\bin;$env:HPEESOF_DIR\tools\python;$env:HPEESOF_DIR\adsptolemy\lib.win32_64;$env:PATH"
& "$env:HPEESOF_DIR\tools\python\python.exe" script.py
```

If the ADS launcher reports an `HPEESOF_DIR` mismatch, set `HPEESOF_DIR` to the ADS version being launched before opening ADS.

## API Pattern

Prefer `keysight.ads.de` over copying example workspaces:

```python
import keysight.ads.de as de
from keysight.ads.de import db_uu as db

if de.workspace_is_open():
    de.close_workspace()

workspace = de.create_workspace(workspace_path)
workspace.open()
de.create_new_library("sipi_case_lib", workspace.path / "sipi_case_lib")
workspace.add_library("sipi_case_lib", workspace.path / "sipi_case_lib", de.LibraryMode.NON_SHARED)

design = db.create_schematic("sipi_case_lib:spec_check:schematic")
design.save_design()
workspace.close()
```

## Known-Good Code Patterns

Use these as starting skeletons before writing new ADS automation. Adapt names,
paths, symbols, and equations from the active `design_strategy.yaml`; do not
copy these as compliance content without replacing the case-specific values.

### ADS Python runner

Run ADS scripts with ADS Python and a matching `HPEESOF_DIR`:

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_ads_python(script: Path, hpeesof_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HPEESOF_DIR"] = str(hpeesof_dir)
    env["COMPL_DIR"] = str(hpeesof_dir)
    env["SIMARCH"] = "win32_64"
    env["PATH"] = (
        str(hpeesof_dir / "bin")
        + os.pathsep
        + str(hpeesof_dir / "tools" / "python")
        + os.pathsep
        + str(hpeesof_dir / "adsptolemy" / "lib.win32_64")
        + os.pathsep
        + env.get("PATH", "")
    )
    ads_python = hpeesof_dir / "tools" / "python" / "python.exe"
    return subprocess.run(
        [str(ads_python), str(script)],
        cwd=str(script.parent),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
```

### Workspace creation without fake `workspace.ads`

Do not create a hand-written `workspace.ads` file. Let ADS create the OA
workspace files:

```python
from pathlib import Path
import keysight.ads.de as de
from keysight.ads.de import db_uu as db

workspace_path = Path(r"D:\case\bench\ads_bench_wrk")
workspace_path.mkdir(parents=True, exist_ok=True)

if de.workspace_is_open():
    de.close_workspace()

workspace = de.create_workspace(workspace_path)
workspace.open()

lib_path = workspace_path / "sipi_bench_lib"
lib_path.mkdir(exist_ok=True)
de.create_new_library("sipi_bench_lib", lib_path)
workspace.add_library("sipi_bench_lib", lib_path, de.LibraryMode.NON_SHARED)

design = db.create_schematic("sipi_bench_lib:spec_check:schematic")
# Place symbols through the ADS database API here, then save.
design.save_design()
workspace.close()
```

### Touchstone file handling

Copy the verified Touchstone into workspace `data/` and reference only the
plain filename inside ADS. Do not use `@channel.s16p`:

```python
from pathlib import Path
import shutil

workspace = Path(r"D:\case\bench\ads_bench_wrk")
touchstone = Path(r"D:\case\simulation\channel.s16p")
data_dir = workspace / "data"
data_dir.mkdir(parents=True, exist_ok=True)
ads_touchstone = data_dir / touchstone.name
shutil.copy2(touchstone, ads_touchstone)

ads_file_parameter = touchstone.name  # e.g. File="channel.s16p"
```

### Netlist smoke execution

Use the matching ADS `hpeesofsim`, isolate each run directory, and treat syntax
errors as hard blockers:

```python
from pathlib import Path
import os
import subprocess


def run_hpeesofsim(netlist: Path, run_dir: Path, hpeesof_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HPEESOF_DIR"] = str(hpeesof_dir)
    env["COMPL_DIR"] = str(hpeesof_dir)
    env["SIMARCH"] = "win32_64"
    env["PATH"] = str(hpeesof_dir / "bin") + os.pathsep + env.get("PATH", "")
    sim = hpeesof_dir / "bin" / "hpeesofsim.exe"
    cp = subprocess.run(
        [str(sim), str(netlist)],
        cwd=str(run_dir),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    log_text = cp.stdout + "\n" + cp.stderr
    (run_dir / f"{netlist.stem}.hpeesofsim.log").write_text(log_text, encoding="utf-8")
    syntax_error = "syntax error" in log_text.lower() or "parse error" in log_text.lower()
    datasets = list(run_dir.glob("*.ds"))
    return {
        "returncode": cp.returncode,
        "success": cp.returncode == 0 and not syntax_error and bool(datasets),
        "syntax_error": syntax_error,
        "datasets": [str(p) for p in datasets],
    }
```

### Per-victim-lane ChannelSim closeout

For an N-lane eye/mask requirement, call the repository runner instead of
hand-writing N Eye Probe components into one ChannelSim netlist:

```powershell
cd <repo>\sipi_harness
node scripts\run_ads_python.mjs scripts\run_ads_per_lane_eye_report.py `
  --workspace <case-dir>\bench\ads_bench_wrk\per_lane_eye_wrk `
  --touchstone <case-dir>\bench\ads_bench_wrk\data\channel_eye_interp.s16p `
  --lane-count 8 `
  --data-rate-gbps 4 `
  --summary <case-dir>\bench\ads_bench_wrk\reports\ads_per_lane_eye_report.json
```

The JSON is valid for closeout only when all of these are true:

```json
{
  "status": "ok",
  "lane_count_requested": 8,
  "lane_count_reported": 8,
  "density_present": true,
  "ber_contour_valid": true
}
```

### Dataset variable audit

Before reporting "BERContour missing", inspect the ADS dataset variables and
look for the full ADS ChannelSim tree:

```python
from pathlib import Path
import keysight.ads.dataset as dataset

ds = dataset.open_dataset(Path(r"D:\case\bench\ads_bench_wrk\data\eye.ds"))
variables = set(ds.var_names())

required = {
    "ChannelSim1.TDM.Eye.EYE_L0",
    "ChannelSim1.TDM.EyeMeasurements.EYE_L0",
    "ChannelSim1.TDM.Eye.BER.EYE_L0",
}
missing = sorted(required - variables)
print("missing:", missing)
print("eye vars:", sorted(v for v in variables if ".Eye" in v)[:50])
ds.close()
```

## Automation Modes

Keep these modes distinct in reports and summaries.

Before creating a new spec-specific ADS bench, run or inspect the repository
bench workspace once on the target machine. It provides minimal SnP inspection,
loaded AC transfer, 3-lane smoke ChannelSim, and full N-lane ChannelSim
schematic/netlist topology patterns. Generated case/demo artifacts must not use
`template` in workspace, cell, or netlist names; template wording is reserved
for documentation and historical examples only.

```powershell
cd <repo>\sipi_harness
npm run bench:ads-workspace -- --workspace <case-dir>\bench\ads_bench_wrk --port-count <2*lane_count> --overwrite
```

Use the generated `reports/ads_bench_summary.json`,
`reports/*.netlist.log`, and `netlists/channelsim_full_<N>lane_eye.ckt`
as the API/symbol sanity baseline. When ADS-DE netlisting succeeds, the
runnable `.ckt` files must be promoted from those ADS-generated schematic
netlist logs. Do not run a hand-written minimal ChannelSim `.ckt` for eye/BER
closure. For N-lane ChannelSim, the generated schematic netlist must show the
full S(2N)P lane-pair order, for example
`S16P:... tx0 rx0 ... tx7 rx7 0`, with `File="channel.s16p"` and no `@`
prefix. Do not copy a smoke/example bench into a compliance result without replacing the
source/load/model, Touchstone port order, and equations from the active
strategy/spec.

If the active spec extracts requirements that generic checks cannot close, first
generate the case-local adapter contract. Normalize Touchstone port order first
when HFSS exports ports in a different physical order than the case-local ADS
bench expects:

```powershell
cd <repo>\sipi_harness
npm run touchstone:reorder-ports -- --input <channel.sNp> --output <channel_ordered.sNp> --lane-count <N> --summary <case-dir>\simulation\hfss3dlayout\touchstone_port_order_summary.json
npm run plan:bench-adapter -- --strategy <case-dir>\strategy\design_strategy.yaml --out-dir <case-dir>\strategy\adapter_plan
npm run bench:ads-workspace -- --workspace <case-dir>\bench\ads_bench_wrk --port-count <2*lane_count> --overwrite
```

The default repository runtime does not ship interface-specific compliance
adapters. Strategy generation must first produce source-derived
`required_benches` and either generic implementation benches or
`blocked_benches`. Convert each blocked bench into a case-local adapter from the
generated contract, with reviewed loading models, equations, lane coverage,
target BER/mask rules, and plot/report extraction. Do not adapt a 3-lane smoke
template to a full N-lane compliance claim.

### 1. Workspace / schematic construction

Use this when the deliverable is an inspectable ADS workspace:

- Create or open a workspace with `keysight.ads.de`.
- Create libraries and cells through the DE Python API.
- Place SnP, source/load, R/C, controller, probe, and display elements from the
  strategy/spec bench definition.
- Copy Touchstone files into the workspace `data/` folder.
- Save a summary with workspace path, library, cell, schematic name, SnP file,
  port order, and required human visual checks.
- Export or create a netlist audit (`*.netlist.log`) from the generated
  schematic when the ADS API supports it. A schematic that cannot netlist is not
  a valid bench handoff.

For a spec-defined compliance bench, this mode is the default completion path:
create an inspectable workspace and schematic, then generate a netlist/dataset
from that schematic. A netlist-only implementation is allowed as an intermediate
debug step, but it does not close the Bench stage unless the engineer explicitly
requested a netlist-only diagnostic.

Do not claim the bench is valid just because the workspace opens. Validate
connectivity and file paths.

Do not create a fake `workspace.ads` placeholder file in a generated ADS
workspace directory. ADS GUI can interpret that placeholder as a workspace file
and report "Invalid workspace file." A valid ADS workspace directory should
contain the ADS-generated `lib.defs`, `cds.lib`, preferences, libraries, `data/`,
and report artifacts, but no hand-written `workspace.ads` shell file.

### 2. Netlist / simulator execution

Use this when the deliverable is a deterministic simulator run, smoke test, or
metric extraction independent of GUI schematic placement:

- Generate an explicit `.ckt` netlist from the strategy/spec bench definition.
- For ChannelSim eye benches, prefer the ADS-DE exported schematic netlist over
  any hand-written `.ckt`. The accepted netlist must preserve Eye Probe
  ModelExtractor defaults such as `Save_Density=yes`, `Save_Contour=yes`,
  `Save_WidthAtBER=yes`, `Save_HeightAtBER=yes`, and
  `BERContour=list(<target BER>)`.
- Before running ChannelSim eye/BER benches, audit the verified EM Touchstone
  frequency grid. If the grid is too sparse for eye simulation, create a
  case-local interpolated Touchstone in the ADS workspace `data/` folder and
  run the eye bench with that file. Use complex linear interpolation in RI
  domain, preserve the original port order, and record the original filename,
  interpolated filename, point counts, frequency range, max frequency step, and
  interpolation method in `eye_touchstone_preprocess_summary.json`. This is a
  deterministic analysis input preparation step, not permission to synthesize
  proxy S-parameters.
- Run `hpeesofsim` from the matching ADS installation.
- Write `netlist.log` or `<bench>_hpeesofsim.log`, the `.ds` dataset, and a JSON
  run summary.
- Put final datasets under the workspace `data/` folder when they are meant to
  be opened by DDS.
- Mark the result as `netlist-driven` if no equivalent schematic was generated
  and visually checked.

Do not use a passing netlist-only result to imply that a schematic is connected
correctly. The two checks are related but separate.
If the strategy/spec requires an ADS bench and the final deliverable is meant to
be reviewed by another engineer, the run summary must say one of:

- `bench_mode: schematic_plus_netlist` when the ADS workspace/schematic exists
  and the exported netlist/dataset validates connectivity.
- `bench_mode: netlist_only_diagnostic` when only a `.ckt`/`hpeesofsim` run was
  produced; this is not a compliance closure.
- `bench_mode: blocked_missing_schematic` when the simulator netlist works but
  the inspectable schematic could not be generated.

### 3. DDS / report generation

Use this when the deliverable is a visual or PDF report:

- DDS files must point to datasets that exist under `data/`.
- Plots should identify whether values came from ADS dataset variables,
  Touchstone post-processing, or a proxy script.
- If a DDS opens with a missing dataset warning, fix the dataset path before
  reporting results.
- For ADS ChannelSim schematic benches, the report extractor must first inspect
  the schematic-run dataset in the workspace `data/` folder, for example
  `data/channelsim_full_<N>lane_eye.ds`. Netlist smoke runs may create
  smaller diagnostic datasets under `netlist_runs/`; do not use those as the
  preferred eye/mask report source when a `data/*.ds` schematic result exists.
  Preserve existing `data/*.ds` results when regenerating ADS bench workspaces.
  A `netlist_runs/*.ds` dataset may be used for automated extraction only when
  its `.ckt` was promoted from an ADS-DE exported schematic netlist and the
  dataset proves density plus BERContour variables are present.
- When eye/mask requirements exist, the report must include three coordinated
  eye views from the ADS result dataset:
  - eye density plot,
  - BER contour plot at the required target BER,
  - rectangular or spec-defined eye mask overlay.
  For lane-count N, the report must cover every victim lane, not only lane 0.
  Run a per-victim ChannelSim sweep when ADS cannot reliably save multiple eye
  probes in one run, then combine all N eye density/BERContour/mask plots into
  the final report. A single-victim eye is a smoke/diagnostic result only.
  Known failure mode: placing multiple Eye Probe/ModelExtractor components in a
  single ChannelSim netlist can make `hpeesofsim` crash or leave a dirty partial
  dataset on some ADS versions. Also, shortened hand-written Eye Probe netlists
  can produce trivial or two-point density arrays. Use the ADS-DE exported
  ModelExtractor parameter set as the per-lane netlist pattern, run one victim
  lane per simulator run, and combine the datasets after all lanes complete.
  Put density, contour, and mask in the PDF/PNG report with shared labels for
  time/UI, voltage, target BER, measured width/height, and pass/fail margin.
  Do not substitute density color plots for BER contour metrics.
- Run the case-local plot export before stage reporting; a text-only pass/fail
  report is not complete. The adapter should write its PDF/Markdown/PNG/JSON
  artifacts into `<case-dir>/reports` or `<case-dir>/bench/.../reports`, and
  `report:stages --bench-workspace <ads workspace>` should make
  `03_bench_report.pdf` include the frequency-domain and eye/mask figures.

### 4. Spec-neutral S-parameter fallback

Use this only when a valid Touchstone file exists and the case strategy/spec
evidence does not contain a governing spec bench, exact pass/fail equation,
explicit loading model, eye/mask/BER requirement, or transient/statistical
metric.

- Create an ADS/SnP inspection workspace and copy the Touchstone into `data/`.
- Generate plots for insertion loss, return loss, and crosstalk where the port
  count supports those metrics.
- When strategy/spec text contains candidate limits, include a result-vs-spec
  overlay plot in the report. Plot measured curves and spec lines on the same
  figure, and mark extracted limits as candidate overlays unless reviewed
  tier-0 evidence is present.
- When eye/mask requirements exist, the report step must receive ADS Eye Probe
  BER contour data. Configure Eye Probe with `Save_Contour=yes`,
  `BERContour=list(<target BER>)`, `Save_WidthAtBER=yes`, and
  `Save_HeightAtBER=yes`, then pass the extracted contour/width/height JSON to
  the report step so the eye density, BER contour, and rectangular/spec mask
  are plotted together. Missing contour data is a bench blocker, not a
  successful report. Use a placeholder mask only with an explicit diagnostic
  override.
- Write PDF, Markdown, PNG, and JSON summaries under `reports/`.
- Mark the result as sanity/proxy evidence. Do not call it compliance unless a
  reviewed spec explicitly accepts those S-parameter metrics and limits.
- If VTF, XT equations, R/C loading, eye diagram, eye mask, BER contour,
  bathtub, jitter, or another spec-defined benchmark has been extracted, this
  fallback is blocked as the Bench stage result. It may be created only as an
  explicit diagnostic supplement after the spec-defined bench is implemented or
  blocked with evidence.

Command:

```powershell
cd <repo>\sipi_harness
npm run bench:sparameter -- --workspace <case-dir>\bench\sparameter_wrk --touchstone <channel.sNp> --strategy <case-dir>\strategy\design_strategy.yaml --overwrite
```

In Stage Review Mode, pause before running ADS/bench verification and show the
engineer the setup review:

```powershell
cd <repo>\sipi_harness
npm run prompt:stage-review -- --stage ads --case-dir <case-dir> --touchstone <channel.sNp>
```

Do not cross this gate until the Touchstone mapping, port order, workspace
target, exact spec equation/loading status, fallback/proxy status, and expected
report outputs are reviewable.

## Harness Rules

1. Build ADS benches from the case strategy/spec equations, not from example schematics.
2. Copy Touchstone files into the workspace `data/` folder unless a verified absolute path is required.
3. For ADS SnP components, use the filename exactly as ADS expects. Do not accidentally prefix `@`; if the file is in `data/`, use the plain filename such as `channel.s16p`.
4. Match SnP component type and port count to the Touchstone file. Use generic `SnP` for multiport files when fixed `S2P/S4P/S8P/S16P` symbols are awkward.
5. Add short wires and assign net labels to wires rather than typing labels directly on SnP pins when pin labeling is fragile. Attach the reference pin to `gnd!`.
6. For fixed SnP symbols, do not infer port order from visual placement or
   `get_inst_term_iter()` order. Use ADS `term_number` and verify the generated
   netlist line has the intended order, for example `S6P:... p1 p2 p3 p4 p5 p6 0`.
7. Validate schematics twice:
   - Visual check in ADS GUI for broken nodes, wrong source polarity, overlapping text, missing SnP file, and unconnected loads.
   - Netlist/dataset check for actual nodes, component values, source polarity, and file paths.
   Save the connectivity audit under `reports/` and include it in the bench summary.
   - Run `npm run check:ads-workspace -- --workspace <workspace> --netlist <workspace>\reports\<bench>.netlist.log --port-count <N> --summary <workspace>\reports\ads_workspace_check.json` for SnP benches. The check must confirm there is no fake `workspace.ads` placeholder and that fixed SnP netlists use `p1 ... pN 0` in electrical port order.
   - For ChannelSim full-lane benches, the same check must accept and record
     lane-pair order `tx0 rx0 ... tx<N-1> rx<N-1> 0`. Any repeated lane node,
     ADS internal `N__*` node, unquoted file path, or `File=@...` token is a
     schematic connectivity failure to repair before reporting.
8. When a spec requires explicit loading, instantiate R/C/Cap elements. Do not replace a required RC model with a generic termination unless the report says it is an approximation.
9. For ChannelSim eye/mask checks, use ADS output variables directly when available. For BER contour masks, use the Eye Probe `BERContour`/contour width and height outputs at the target BER rather than reconstructing from density images.
   Reports for eye/mask requirements must show density, BER contour, and mask
   overlay together; density alone is only a visualization, not a pass/fail
   metric.
10. For ultra-low BER requirements, enable the ADS ChannelSim ultra-low BER mode when the target is below the default simulation floor. The accepted simulator log must confirm the equivalent of the GUI option "Enable ultra low BER (<1e-16) simulation"; otherwise rerun bench generation instead of reporting "open BER contour missing."
11. Before ChannelSim eye/BER simulation, check Touchstone frequency sampling.
    If sparse, run `npm run touchstone:resample-eye -- --input <channel.sNp>
    --output-dir <ads-workspace>\data --data-rate-gbps <rate>` or the equivalent
    integrated `bench:ads-from-strategy` path. The eye netlist must reference
    the resulting dense `_eye_interp.sNp` file when interpolation was triggered.
12. DDS files should reference datasets that actually exist under the workspace `data/` folder. If a DDS opens with a missing dataset warning, fix the dataset path before claiming results.
13. If a spec-specific bench, loading model, or pass/fail equation exists in the governing source, implement that bench before making a compliance claim. Do not replace it with the spec-neutral SnP fallback.
14. Before choosing the spec-neutral SnP fallback, review the strategy's compliance metric coverage matrix. If the governing source contains transient/statistical requirements such as eye diagram, eye mask, BER contour, bathtub, jitter, or timing margin, create the required bench or mark the result blocked; do not treat insertion-loss/crosstalk plots as a substitute.
15. If no spec-specific bench is available, still produce the spec-neutral SnP fallback report so the stage has inspectable IL/RL/XT evidence and an explicit proxy status.
16. If a spec-specific bench is detected but cannot be implemented yet, mark the Bench stage `blocked_missing_spec_bench_implementation` instead of running the fallback as the stage result. Do not use `bench:sparameter` to close the Bench stage in this case.
17. For lane-count N crosstalk or eye benches, use the full S(2N)P Touchstone unless the spec explicitly defines a reduced subchannel method. Run every required victim lane and include all N-1 aggressor lanes when the spec defines aggressor-inclusive metrics. A 3-lane `.s6p` example is a smoke check only and cannot close an x8/x16/x32 compliance bench.
    For eye/mask/BERContour, the default closeout is one victim-lane ChannelSim
    run per lane plus one combined N-panel report. A lane-0-only eye report is
    not sufficient for an N-lane compliance bench.
    Do not "fix" this by putting all Eye Probe components into one ChannelSim
    run unless that exact ADS version has been proven to save all datasets
    cleanly. The robust generic path is per-lane victim simulation with the
    other lanes configured as aggressors.
18. ADS failure is not a reason to generate proxy datasets. Keep repairing the real workspace, schematic/netlist, dataset, DDS/report, and BER contour extraction until the required artifacts exist, or mark Bench blocked with logs.
19. ADS syntax errors are hard Bench blockers. Run generated netlists in a clean
    run directory through the matching ADS `hpeesofsim`, scan the captured
    `netlist.log` for syntax/parse errors, and repair the generated netlist
    before accepting any dataset or report.
20. Do not silently switch from schematic-based ADS construction to netlist-only
    execution. If a schematic cannot be generated, record the API/symbol/OA-lock
    failure and keep the Bench stage blocked unless the user explicitly accepts a
    netlist-only diagnostic.
21. Legacy microstrip scripts such as `create_ads_channel_workspace.py`,
    `create_ads_channel_schematic.py`, and `run_ads_channel_sim.py` are historical
    coupon examples. Do not use them as the generic multi-lane/spec bench path.
22. Do not finish a Bench or Report stage with only text pass/fail tables when
    metric plots are available or required. VTF/XT reports need measured
    frequency-vs-loss and frequency-vs-crosstalk curves with spec overlays. Eye
    reports need density, BERContour, and mask overlay figures.

## Stage Outputs

For each ADS/spec-check stage, produce:

- ADS workspace path.
- Library/cell/schematic name.
- Touchstone filename and port order.
- Dataset path and simulator log.
- DDS or equivalent plot/report.
- For eye/mask requirements, PNG/PDF plots containing eye density, BER contour
  at target BER, and the rectangular/spec mask overlay.
- JSON summary with exact equations, limits, pass/fail, and whether the result is exact or proxy.
- `03_ads_spec_check_report.pdf` through `sipi_harness/scripts/generate_stage_pdf_reports.py`.

## Common Failure Modes To Avoid

- Opening only ADS executable without opening the intended workspace.
- Generating schematic symbols with disconnected TX/RX nodes.
- Using `Term` symbols when the spec requires separate R and C loading.
- Forgetting RX load capacitance or aggressor loading in crosstalk benches.
- Creating a correct-looking `.ds` or deterministic report from a separate script while the schematic itself is invalid.
- Reading eye density images as if they are mask metrics; use contour variables at the required BER.
- Running a simplified hand-written ChannelSim netlist when ADS-DE already
  exported a schematic netlist. This often drops Eye Probe defaults and causes
  false "BERContour missing" failures even though the schematic can generate
  density and contour correctly.
- Feeding ChannelSim eye/BER with an undersampled EM Touchstone. If the
  frequency grid is sparse, first create and record an interpolated
  `_eye_interp.sNp` file with `touchstone:resample-eye` or the integrated
  `bench:ads-from-strategy` preprocessing step, then run the eye bench from
  that file.
- Running only the fallback S-parameter report when the governing spec defines
  explicit loading, transfer-function, crosstalk, eye/mask, jitter, or BER
  benches. Fallback reports are smoke/proxy evidence, not compliance.
- Treating the fallback S-parameter report as the final Bench stage artifact
  when VTF/XT/eye/mask/BER evidence exists. The correct result is either the
  spec-defined bench output or a blocked Bench stage with the missing
  implementation listed.
- Failing to audit metric coverage before bench creation. The ADS bench plan
  must account for every requirement family discovered from the governing
  source, including time-domain/statistical metrics that are not visible in
  S-parameter plots.
- Using a 3-lane `.s6p` or smoke check for a full multi-lane requirement.
  The compliance bench must cover the active lane count and aggressor set.
- Reporting only `EYE_L0` for an N-lane eye/mask requirement. Generate and
  validate every victim lane, then include the all-lane eye plot and per-lane
  JSON summary in the final report.
- Adding all lane Eye Probe components into one ChannelSim run and accepting a
  dirty dataset after `hpeesofsim` crashes. Treat dirty/partial `.ds` output as
  a failed run. Use per-victim lane runs with ADS-DE ModelExtractor settings.
- Using `template` in generated demo/case workspace, cell, or netlist names.
  Use case-local names such as `ads_bench_wrk` and
  `channelsim_full_8lane_eye`.
