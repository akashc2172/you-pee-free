# COMSOL First Runs: Baby Steps (v1 Contract)

This is the exact first-time workflow for one run using the campaign defaults:
- `sim_contract_version = v1_deltaP490_steady_laminar`
- pressure-driven flow: `p_in = 490 Pa`, `p_out = 0 Pa`
- triple-domain dumbbell fluid region
- no-slip walls, water-like fluid

Important boundary:
- Python does not build this COMSOL template for you.
- Python batch execution only begins after the `.mph` and its adjacent `.contract.json` sidecar have been prepared correctly.
- Before the first real run, use [`docs/comsol_smoke_run_checklist.md`](/Users/akashc/masters/docs/comsol_smoke_run_checklist.md).
- For regenerated CAD, use [`docs/comsol_normalized_frame_reference.md`](/Users/akashc/masters/docs/comsol_normalized_frame_reference.md) when laying out the dumbbell domain and coordinate boxes.
- Before placing the dumbbell cylinders, run `scripts/print_comsol_template_values.py` for the exact body-centered cylinder and box coordinates for your design.

## 0) Generate one STEP design from the pipeline

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_optimization_campaign.py --campaign first_run --init_lhs --n_init 1
```

Expected files:
- `data/campaigns/first_run/cad/design_0000.step`
- `data/campaigns/first_run/batch_0000.csv`

## 1) Build the canonical COMSOL template once

1. Open COMSOL -> `Model Wizard` -> `3D`.
2. Add physics: `Single-Phase Flow` -> `Laminar Flow (spf)`.
3. Study: `Stationary`.
4. In `Geometry 1`, add `Import` and select `design_0000.step`.
5. Add three cylinders for external fluid:
- kidney reservoir (larger top)
- ureter tube (narrow middle)
- bladder reservoir (larger bottom)
6. Union the three cylinders.
7. Difference: `fluid_envelope - stent_solid`.
8. Build all.

Important: after Difference, you should have one fluid domain around/inside the stent void.

## 2) Create robust named selections

Create explicit named selections. Python does not create or verify them directly inside COMSOL; it only requires the sidecar contract to attest that they exist.
- `inlet`: top reservoir cap face
- `outlet`: bottom reservoir cap face
- `stent_walls`: all fluid boundaries except inlet/outlet
- `coil_zone` and `mid_zone` via coordinate-based boxes

## 3) Set physics (fixed campaign contract)

In Laminar Flow:
- Density: `1000[kg/m^3]`
- Dynamic viscosity: `0.001[Pa*s]`
- Inlet BC: Pressure `490[Pa]` on `inlet`
- Outlet BC: Pressure `0[Pa]` on `outlet`
- Walls: No Slip on `stent_walls`

## 4) Mesh for small holes

1. Start with Physics-controlled `Fine`.
2. Add local `Size` node on `stent_walls` with `Finer` or `Extra fine`.
3. Build mesh.
4. Check log for `Minimum element quality`.

Campaign QC gate: minimum element quality must be `> 0.05` (target `> 0.1`).

## 5) Solve and verify trust checks

Run `Study 1 -> Compute`.

Evaluate:
- `spf.inl1.pAverage` (inlet pressure)
- `spf.out1.pAverage` (outlet pressure)
- `spf.out1.volumeFlowRate`
- `abs(spf.inl1.volumeFlowRate + spf.out1.volumeFlowRate)/max(abs(spf.inl1.volumeFlowRate),abs(spf.out1.volumeFlowRate))`

QC gate: mass balance error must be `< 0.01`.

## 6) Save template and sidecar contract for batch orchestration

Save template as:
- `data/comsol_templates/base_flow_v1.mph`

Create the adjacent sidecar file:
- `data/comsol_templates/base_flow_v1.contract.json`

The sidecar must attest these exact fields:
- `sim_contract_version`
- `domain_template`
- `selection_strategy`
- `required_named_selections`
- `required_exports`

For the current hardened runner, the sidecar must declare:
- `domain_template = triple_domain_dumbbell`
- `selection_strategy = coordinate_bbox`
- named selections: `inlet`, `outlet`, `stent_walls`, `coil_zone`, `mid_zone`
- exports: `results_csv`, `realized_geometry_csv`

Template parameters expected by scripts:
- `cad_path`
- `design_id`
- `p_inlet_pa`
- `p_outlet_pa`
- `delta_p_pa`
- `sim_contract_version`
- `domain_template`
- `selection_strategy`

The COMSOL template also needs exports that produce, for each run:
- `<run_id>_results.csv`
- `<run_id>_realized_geometry.csv`

Without the realized-geometry export, a run cannot become `valid`.

## 7) Run Python batch orchestration

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_comsol_campaign.py \
  --campaign first_run \
  --base_mph data/comsol_templates/base_flow_v1.mph
```

Outputs:
- per-run folders in `data/campaigns/first_run/comsol_runs/`
- checkpoint CSV for resume
- batch results CSV
- merged `data/campaigns/first_run/results.csv`
- attempt-scoped subdirectories so retries do not reuse stale artifacts

## Troubleshooting (quick)

### I only see a cylinder and no stent mesh
- You are likely viewing Geometry, not Mesh.
- In Model Builder, click `Mesh 1 -> Build All`.
- In Graphics toolbar, enable mesh display (wireframe/mesh overlay).
- Confirm Difference was built as `fluid_envelope - stent_solid`; otherwise the stent may have been removed incorrectly.

### Solver finished but results look suspicious
- Check mass balance error first.
- Check inlet/outlet selections were not swapped.
- Check minimum element quality in the log.

### One run fails in a big batch
- Re-run the same command; checkpoint resume is enabled by default.
- Failed runs are recorded with explicit `run_status` and `failure_class`.
- If the template sidecar is missing or does not attest the required selections/exports, the run will fail closed as `failed_geometry` / `failed_selection`.
