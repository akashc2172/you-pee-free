# Repository Layout (Hardening v1)

Canonical active layout for ongoing campaign execution:
- `src/` source modules
- `config/` canonical campaign/simulation config
- `scripts/` runnable entrypoints
- `data/campaigns/<campaign>/` generated campaign artifacts
- `runs/` local orchestration scratch/checkpoints
- `results/` analysis-ready exports
- `artifacts/` stable outputs for sharing
- `archive/` retired or superseded experiments

## Active entrypoints
- Geometry/candidate generation: `scripts/run_optimization_campaign.py`
- COMSOL batch solve + QC + checkpoint/resume: `scripts/run_comsol_campaign.py`
- Unified CLI wrappers: `src/cli.py`

## Rule of thumb
- Keep one canonical execution path for production runs.
- Keep exploratory notebooks/scripts outside the active campaign path.
- Move stale run products into `archive/` rather than deleting provenance.
