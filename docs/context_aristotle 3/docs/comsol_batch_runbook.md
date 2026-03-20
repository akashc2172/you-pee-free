# COMSOL Batch Runbook (Python Orchestration + Manual Template)

## Purpose
Run `>=180` designs with deterministic Python-side orchestration and fail-closed QC, while being explicit about the COMSOL work that still has to exist in the template.

For the first real validation run, start with [`docs/comsol_smoke_run_checklist.md`](/Users/akashc/masters/docs/comsol_smoke_run_checklist.md) instead of launching a batch immediately.
For metadata-driven shaft-hole automation, also use [`docs/comsol_shaft_hole_flux_automation.md`](/Users/akashc/masters/docs/comsol_shaft_hole_flux_automation.md).

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

## Fixed-length campaign generation

For the hardened two-length study, generate separate campaigns instead of sampling `stent_length` continuously:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_optimization_campaign.py \
  --campaign campaign_len140 \
  --init_lhs \
  --n_init 60 \
  --fixed-param stent_length=140
```

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_optimization_campaign.py \
  --campaign campaign_len220 \
  --init_lhs \
  --n_init 60 \
  --fixed-param stent_length=220
```

Use separate manually prepared templates:
- `campaign_len140` -> `data/comsol_templates/base_flow_len140_v1.mph`
- `campaign_len220` -> `data/comsol_templates/base_flow_len220_v1.mph`

Template construction is currently manual once per length/template. Batch execution is automated after the template exists.

Exact smoke commands:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/debug_comsol_smoke_run.py \
  --base_mph /Users/akashc/masters/data/comsol_templates/base_flow_len140_v1.mph \
  --cad_file /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.step \
  --output_dir /Users/akashc/masters/data/campaigns/campaign_len140/smoke_runs \
  --design_id design_0000 \
  --comsol_exec comsol
```

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/debug_comsol_smoke_run.py \
  --base_mph /Users/akashc/masters/data/comsol_templates/base_flow_len220_v1.mph \
  --cad_file /Users/akashc/masters/data/campaigns/campaign_len220/cad/design_0000.step \
  --output_dir /Users/akashc/masters/data/campaigns/campaign_len220/smoke_runs \
  --design_id design_0000 \
  --comsol_exec comsol
```

Exact batch commands:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_comsol_campaign.py \
  --campaign campaign_len140 \
  --base_mph /Users/akashc/masters/data/comsol_templates/base_flow_len140_v1.mph \
  --comsol_exec comsol
```

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_comsol_campaign.py \
  --campaign campaign_len220 \
  --base_mph /Users/akashc/masters/data/comsol_templates/base_flow_len220_v1.mph \
  --comsol_exec comsol
```

## What Python now enforces
- Canonical simulation contract fields are stamped into each run.
- COMSOL runtime inputs are strict-whitelisted; manifest metadata and JSON/list fields are not forwarded to `-pname/-pval`.
- The batch runner refuses to trust a template unless the adjacent sidecar contract attests:
  - `domain_template = triple_domain_dumbbell`
  - `selection_strategy = coordinate_bbox`
  - required named selections: `inlet`, `outlet`, `stent_walls`, `coil_zone`, `mid_zone`
  - required exports: `results_csv`, `realized_geometry_csv`
- Recommended baseline scientific-output selections, not yet hard-gated:
  - `sel_holes_prox`
  - `sel_holes_mid`
  - `sel_holes_dist`
  - `sel_wall_global`
- Per-run provenance is written to `<run_id>_provenance.json`.
- If the results CSV includes grouped hole/WSS outputs, Python also derives:
  - `q_sh_total_signed`
  - `q_sh_total_abs`
  - `hole_uniformity_cv_grouped`
  - `hole_uniformity_maxmin_grouped`
  - `fraction_partition_lumen`
  - `fraction_partition_holes`
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

## Solver strategy note

For the current stationary templates, continuation should be the default solve strategy.

Recommended ramp path:
- define `p_ramp`
- inlet pressure = `p_ramp*490[Pa]`
- auxiliary sweep = `0.1 0.5 1.0`

## Surrogate ingestion rule
Train only on rows with `run_status == valid`.
Keep invalid/failure rows for diagnostics and reproducibility.
