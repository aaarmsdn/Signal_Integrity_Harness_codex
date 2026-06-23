# Sample Expected Outputs

The sample case is a dry-run/install check. It does not require KiCad, AEDT, or
ADS licenses.

Expected files after running:

- `outputs/sample_case/manifest.json`
- `outputs/sample_case/reports/harness_run_summary.md`
- `outputs/sample_case/logs/harness.log`

The manifest should report:

- `status: DRY_RUN_READY`
- 4 port intents
- all input schema checks passing
- EDA execution stages listed as planned, not executed
