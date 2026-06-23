# Examples

Examples demonstrate how to adapt the generic harness to a concrete workflow.
They are not the default execution path.

## Rules for Examples

- Keep sample data small and redistributable.
- Keep proprietary specs, books, board databases, AEDT projects, ADS workspaces,
  and Touchstone results out of Git unless redistribution rights are explicit.
- Put application-specific constants in the example config or input files, not
  in generic scripts.
- If an example script becomes useful for multiple cases, extract the reusable
  part into `scripts/` or `scripts/lib/` and keep only example parameters here.

## Available Examples

- `sample_case/`: EDA-free dry-run that validates config, stackup, bump map,
  port intents, manifest writing, and report summary generation.

## Run the Sample

```powershell
cd <repo>\sipi_harness
npm run smoke:sample
```
