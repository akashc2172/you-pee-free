# COMSOL Batch Runbook (Python Orchestration + Manual Template)

## Purpose
Run `>=180` designs with deterministic Python-side orchestration and fail-closed QC, while being explicit about the COMSOL work that still has to exist in the template.

For the first real validation run, start with [`docs/comsol_smoke_run_checklist.md`](/Users/akashc/masters/docs/comsol_smoke_run_checklist.md) instead of launching a batch immediately.

## Prerequisites
- A generated campaign batch CSV (`batch_XXXX.csv`)
- A manually prepared canonical template MPH
- An adjacent template contract sidecar: `<base_mph_stem>.contract.json`
- COMSOL executable accessible (`comsol` or full path)

## Command

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_comsol_campaign.py \
  --campaign <campaign_name> \
  --base_mph <path/to/base_flow_v1.mph> \
  --comsol_exec comsol
```

Optional flags:
- `--batch_file` to target a specific batch CSV
- `--output_dir` to override run directory
- `--results_file` to override aggregate results path
- `--no_resume` to force rerun without checkpoint resume

## What Python now enforces
- Canonical simulation contract fields are stamped into each run.
- COMSOL runtime inputs are strict-whitelisted; manifest metadata and JSON/list fields are not forwarded to `-pname/-pval`.
- The batch runner refuses to trust a template unless the adjacent sidecar contract attests:
  - `domain_template = triple_domain_dumbbell`
  - `selection_strategy = coordinate_bbox`
  - required named selections: `inlet`, `outlet`, `stent_walls`, `coil_zone`, `mid_zone`
  - required exports: `results_csv`, `realized_geometry_csv`
- Per-run provenance is written to `<run_id>_provenance.json`.
- Retries are attempt-scoped under `attempt_0/`, `attempt_1/`, so stale artifacts are not reparsed.
- A run is only `valid` if all required evidence exists and passes:
  - explicit convergence evidence
  - explicit solver tolerance evidence
  - `ΔP` agreement with the 490 Pa contract
  - finite outputs
  - pressure sign consistency
  - flow sign consistency
  - mass balance `< 1%`
  - mesh quality `> 0.05`
  - COMSOL-exported realized geometry

## What Python does not prove
- Python does not create the `.mph` template.
- Python does not create the COMSOL selections.
- `coordinate_bbox` is enforced only by requiring the sidecar contract to attest that the prepared template already uses it.
- If the template or exports do not satisfy that contract, the run fails closed instead of being treated as hardened.

## Run status meanings
- `valid`: passed QC and safe for surrogate training
- `invalid_qc`: solved but failed trust gates
- `failed_solver`: COMSOL solve did not complete
- `failed_geometry`: geometry/CAD input issue
- `failed_extraction`: output parse/export issue

## Smoke-test ladder
1. Run one design and inspect all output artifacts.
2. Run five designs and verify the same prepared template works without manual boundary reselection.
3. Run twenty designs and verify checkpoint resume by interrupting once.
4. Launch full campaign only after the first three pass.

## Surrogate ingestion rule
Train only on rows with `run_status == valid`.
Keep invalid/failure rows for diagnostics and reproducibility.
