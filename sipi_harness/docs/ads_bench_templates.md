# ADS Bench Workspace Checks

Use this page when an ADS workspace or schematic does not netlist correctly.
The harness keeps ADS schematic construction, netlist simulation, and report
generation as separate checks.

## Golden Bench Command

```powershell
cd <repo>\sipi_harness
npm run bench:ads-workspace -- --workspace <case-dir>\bench\ads_bench_wrk --overwrite
```

The command uses ADS Python and `keysight.ads.de` to create:

- `sparam_snp_check`: generic SnP/Touchstone inspection schematic.
- `ac_loaded_transfer_check`: AC controller, AC source, explicit source R,
  and shunt C/R loading.
- `channelsim_3lane_eye_smoke`: one victim Tx, two Xtlk2 aggressors,
  generic SnP channel, Eye probe, and explicit RC loading. This is a smoke
  topology check only, not an N-lane compliance bench.
- `channelsim_full_<N>lane_eye`: full S(2N)P ChannelSim topology with
  one victim Tx, N-1 Xtlk2 aggressors, explicit RC loading, and Eye probe
  BERContour outputs.

It also writes bench netlists under `netlists/` and schematic netlist audits
under `reports/*.netlist.log` when the ADS API can generate them. When ADS-DE
netlisting succeeds, the runnable `.ckt` files under `netlists/` must be
promoted from the ADS-generated schematic netlist logs, not from hand-written
minimal netlists. This matters for ChannelSim eye benches because ADS emits
Eye Probe ModelExtractor defaults such as `Save_Density=yes`,
`Save_Contour=yes`, `Save_WidthAtBER=yes`, `Save_HeightAtBER=yes`,
`BERContour=list(<target BER>)`, and ultra-low-BER analysis options only in
the full schematic netlist. The full ChannelSim schematic is the inspectable
baseline; a hand-written `.ckt` is only a debug fallback.

## ChannelSim Dataset Priority

For eye/mask reporting, prefer the dataset produced by the ADS schematic run:

```text
<workspace>/data/channelsim_full_<N>lane_eye.ds
```

This is the dataset an engineer sees from the ADS workspace/DDS flow and it
contains the report variables such as:

- `ChannelSim1.TDM.Eye.EYE_L0`
- `ChannelSim1.TDM.EyeMeasurements.EYE_L0`
- `ChannelSim1.TDM.Eye.BER.EYE_L0`
- `ChannelSim1.TDM.Eye.BERWidthList.EYE_L0`
- `ChannelSim1.TDM.Eye.BERHeightList.EYE_L0`

Datasets under `netlist_runs/` are acceptable for automated eye reporting only
when the `.ckt` was promoted from an ADS-DE exported schematic netlist. Before
accepting a ChannelSim eye dataset, verify the simulator log says ultra-low BER
was enabled when the target BER requires it, and verify the dataset contains
both eye density and BER contour variables. A dataset from a hand-written
minimal ChannelSim netlist is a diagnostic only and must not close an eye/mask
bench. When rerunning bench generation, preserve existing `data/*.ds` files
unless the user explicitly asks for overwrite.

## Multi-Lane Eye Closeout

For lane-count N eye/mask requirements, a lane-0 eye is only a smoke result.
The closeout report must cover every victim lane. The robust generic method is:

1. Use the full S(2N)P Touchstone for every run.
2. Run one ChannelSim case per victim lane.
3. Configure the selected lane as the victim Tx/Rx path and all other lanes as
   aggressors when the spec requires crosstalk-aware eye conditions.
4. Use the ADS-DE exported Eye Probe/ModelExtractor parameter set, including
   dense time/amplitude settings and BERContour save flags.
5. Combine all N datasets into one N-panel eye density/BERContour/mask report.

Reason: on some ADS versions, placing multiple Eye Probe/ModelExtractor
components in one ChannelSim run can crash `hpeesofsim` or leave a dirty partial
dataset. A shortened hand-written Eye Probe line can also generate trivial
two-point density instead of the dense eye seen from an ADS schematic run.
Dirty/partial datasets are failed runs, not valid evidence.

## Touchstone Sampling For Eye Simulation

Before ChannelSim eye or BER simulation, check the verified EM Touchstone
frequency sampling. If the input grid is too sparse for eye analysis, generate a
case-local dense file before building/running the eye bench:

```powershell
cd <repo>\sipi_harness
npm run touchstone:resample-eye -- `
  --input <case-dir>\simulation\hfss3dlayout\channel.sNp `
  --output-dir <case-dir>\bench\ads_bench_wrk\data `
  --data-rate-gbps <rate> `
  --summary <case-dir>\bench\ads_bench_wrk\reports\eye_touchstone_preprocess_summary.json
```

The resampler uses complex linear interpolation in RI domain and preserves the
Touchstone port order. If it creates `<channel>_eye_interp.sNp`, the ChannelSim
eye netlist/schematic must reference that dense file. The summary JSON must be
kept with the bench artifacts so reviewers can see the original point count,
interpolated point count, frequency range, and max frequency step. This is not a
proxy-data escape path; it is only allowed after a verified real EM or
measurement Touchstone exists.

## Rules

- Copy Touchstone files into the workspace `data/` folder.
- Use the plain filename in ADS components, for example `channel.s16p`; do not
  prefix it with `@`.
- Prefer short wire stubs with net labels over labels typed directly onto
  component pins.
- Attach the SnP reference pin to `gnd!`.
- For fixed SnP symbols such as `S2P`, `S6P`, or `S16P`, do not infer port
  order from visual pin placement or `get_inst_term_iter()` order. Use ADS
  `term_number` and confirm the generated netlist node order, for example
  `S6P:... p1 p2 p3 p4 p5 p6 0`.
- For ChannelSim lane benches, confirm the generated SnP netlist node order is
  lane-pair ordered, for example `S16P:... tx0 rx0 ... tx7 rx7 0` for x8.
- The SnP `File` value in the generated netlist must be a quoted plain filename
  such as `File="channel.s16p"`. Do not use `@channel.s16p`, and do not leave
  the filename unquoted where hpeesofsim can interpret it as a variable.
- Do not claim schematic validity unless the workspace opens and a netlist
  audit or simulator dataset confirms connectivity.
- Do not read only `netlist_runs/*.ds` when checking eye density or BERContour.
  Search `data/*.ds` first and extract the ADS variables listed above.
- Do not use smoke checks as compliance benches until the active strategy
  replaces their source/load model, port order, equations, and pass/fail limits
  with reviewed spec evidence.
- Generated case/demo workspace, cell, and netlist names must not include
  `template`. Use names such as `ads_bench_wrk` and
  `channelsim_full_8lane_eye`.
- Treat ADS syntax errors as hard blockers. Run generated netlists from a clean
  run directory through the matching ADS `hpeesofsim`, capture the log, scan for
  syntax/parse errors, and repair the netlist before accepting a dataset/report.
- For ChannelSim eye/mask benches, reject any runnable netlist that lacks
  `Save_Density=yes`, `Save_Contour=yes`, `Save_WidthAtBER=yes`,
  `Save_HeightAtBER=yes`, and `BERContour=list(<target BER>)`. If the target BER
  is below the default ChannelSim floor, the log must confirm ultra-low BER
  simulation is enabled.

## When To Use Each Pattern

- Use the SnP check for port-order and file-path inspection.
- Use the AC check for frequency-domain transfer functions or loaded channel
  checks.
- Use the 3-lane eye smoke check only to inspect ChannelSim topology: one victim
  lane, two aggressor lanes, eye probe, and explicit source/receiver loading.
  For a lane-count N compliance bench, build from the full S(2N)P Touchstone,
  run every required victim lane, and include all N-1 aggressors when the spec
  defines crosstalk or eye-with-aggressor conditions. Never close an x8 Bench
  stage with a 3-lane `.s6p` example.
- Use `channelsim_full_<N>lane_eye` as the first ADS sanity target for
  N-lane eye/ChannelSim automation. It must netlist with the full lane-pair SnP
  order and should pass an `hpeesofsim` smoke run after a valid Touchstone is
  copied into the workspace `data/` folder.

If the governing spec defines eye mask, BER contour, bathtub, jitter, or
specific loading, the SnP template alone is not sufficient for compliance.
