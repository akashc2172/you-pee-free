# Stent Optimization Pipeline

This repository automates parametric stent generation, COMSOL batch orchestration, and surrogate-model training.

## Current campaign defaults
- 11 sampled CAD variables (coil geometry locked for v1 stability)
- pressure-driven COMSOL contract: `ΔP = 490 Pa`
- triple-domain dumbbell external fluid region
- QC-gated run statuses: `valid | invalid_qc | failed_solver | failed_geometry | failed_extraction`

## Important limits
- Python does not generate the COMSOL template or named selections.
- Batch runs require a manually prepared `.mph` plus an adjacent template contract sidecar: `<base_mph_stem>.contract.json`.
- `valid` runs require COMSOL-exported results and COMSOL-exported realized geometry; CAD-side geometry summaries are stored as `precomsol_*` only.

## Main commands

Generate one campaign batch and CAD files:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_optimization_campaign.py --campaign first_run --init_lhs --n_init 1
```

Run COMSOL batch orchestration with checkpoint/resume and QC parsing:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_comsol_campaign.py --campaign first_run --base_mph data/comsol_templates/base_flow_v1.mph
```

## Key docs
- `docs/comsol_first_runs_baby_steps.md`
- `docs/comsol_batch_runbook.md`
- `docs/comsol_normalized_frame_reference.md`
- `docs/comsol_smoke_run_checklist.md`
- `docs/parameter_schema.md`
- `docs/pipeline_overview.md`
- `docs/repo_hardening_layout.md`
