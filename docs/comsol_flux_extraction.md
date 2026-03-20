# COMSOL Flux Extraction Framework

## What it is

This is the first metadata-driven extraction layer for the pediatric stent baseline COMSOL model.

It separates:
- geometry generation and feature IDs on the CAD side
- COMSOL dataset / numerical creation on the COMSOL side
- summary aggregation on the Mac/Python side after files already exist

## Why measurement surfaces exist

Per-hole and unroof exchange should not be measured on literal wall boundaries.

Instead, the framework uses dedicated measurement surfaces:
- one cut-plane disk per hole cap
- one cut-plane rectangle for the unroof patch
- one distal lumen cross-section
- one distal annulus cross-section
- stable inlet/outlet reference selections for global flow and pressure

## Files produced by CAD export

For each design:
- `design_XXXX.step`
- `design_XXXX.holes.json`
- `design_XXXX.meters.json`

`*.holes.json` remains the hole/debug sidecar.

`*.meters.json` is the extraction sidecar. It defines feature IDs, classes, centers, normals, and shape parameters used by COMSOL.

The per-feature path is the authoritative extraction path:
- `hole_cap`
- `unroof_patch`
- `cross_section`
- `pressure_ref`

Legacy grouped outputs like `q_sh_prox`, `q_sh_mid`, and `q_sh_dist` are still tolerated for backward compatibility, but new summaries should be derived from the per-feature CSV whenever those files exist.

## COMSOL-side method

Method source:
- [BuildFluxExtractionLayer.java.txt](/Users/akashc/masters/src/comsol/java/BuildFluxExtractionLayer.java.txt)

Expected method inputs:
- `measurement_metadata_path`
- `design_id`

Fallback behavior:
- if `measurement_metadata_path` is empty, the method tries to find `<design_id>.meters.json` next to the output `.mph`

Outputs written by the COMSOL method:
- `<design_id>_flux_scalars.csv`
- `<design_id>_flux_features.csv`

Current smoke-test behavior:
- the method now writes explicit evaluation status columns into both CSVs
- feature CSV rows include:
  - `eval_status`
  - `eval_error`
- scalar CSV rows include:
  - `required_eval_status`
  - `required_eval_error`
- if a cut-plane-backed feature evaluates empty, throws an exception, or returns `NaN`/`Inf`, that status is written to CSV and the method fails after writing the files
- `sec_distal_lumen` and `sec_distal_annulus` are treated as required smoke-test outputs; blank values now fail the method after export

## Sign convention

For exchange features:
- positive signed flux = into the stent lumen
- negative signed flux = out of the lumen

Units:
- volumetric flow: `mL/min`
- pressure: `Pa`
- unroof flux density: `mL/min/mm`

## Current scope

Implemented feature classes in `*.meters.json`:
- `hole_cap`
- `unroof_patch`
- `cross_section`
- `pressure_ref`

Current pragmatic assumption:
- inlet and outlet references reuse stable named selections `inlet` and `outlet`
- distal annulus outer radius is currently based on the validated dumbbell template radius of `4.0 mm`
- the distal lumen / annulus partition plane is now placed strictly upstream of any distal unroof, with one outer-radius clearance margin

Practical consequence:
- the baseline `.mph` must already contain the named selections referenced by the pressure-ref features
- `BuildFluxExtractionLayer` now resolves pressure-ref selections by internal tag first, then by label if needed
- if exactly one label match exists, the method uses that internal tag automatically
- if multiple label matches exist, the method fails with an explicit ambiguity error
- cut-plane-backed feature flux is now evaluated against the explicit metadata normal for that feature, rather than relying on dataset `nx,ny,nz`

## Validation contract

`*.meters.json` is now validated more aggressively before export and before downstream use:
- feature IDs must be unique and follow the expected naming contract
- zones must be valid metadata labels (`prox`, `mid`, `dist`)
- shape parameters must match the declared geometry type
- area values must agree with the shape parameters
- pressure references must use named selections with explicit roles
- hole caps must preserve parent-hole traceability
- distal partition cross-sections must not land inside the unroof interval

Validation warnings are preserved in the sidecar under `validation`.

## Collection / postprocessing

Collector:
- [collect_flux_extraction_results.py](/Users/akashc/masters/scripts/collect_flux_extraction_results.py)

It reads per-design extraction CSVs and writes:
- one-row-per-design summary CSV
- one-row-per-feature long-form CSV

New summary metrics available in the postprocessor:
- `hole_uniformity_gini`
- `exchange_number`
- `hole_only_exchange_number`
- `net_direction_index`
- `hole_flux_centroid_x_mm`
- `hole_flux_spread_x_mm`
- `hole_flux_dominance_ratio`
- `frac_unroof_of_exchange_total`

Invariant/QC checks are also surfaced in the summary:
- `invariants_passed`
- `invariant_warnings`

## Commands

Generate CAD + metadata:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/run_optimization_campaign.py \
  --campaign campaign_len140 \
  --init_lhs \
  --n_init 5 \
  --fixed-param stent_length=140
```

Collect extraction outputs after copying COMSOL results back:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/collect_flux_extraction_results.py \
  --results-dir /absolute/path/to/comsol_results \
  --summary-out /absolute/path/to/flux_summary.csv \
  --features-out /absolute/path/to/flux_features.csv
```

## Intentional current limits

- I did not claim to run COMSOL here.
- `mesh_ndof` is still left for future direct extraction or log enrichment.
- Inlet/outlet reference surfaces still rely on stable named template selections, not imported `meters.step` geometry.
- Coil-hole cap placement in `*.meters.json` currently inherits the exported coil-hole center/axis rule; it can be refined later with dedicated coil-mouth reconstruction if needed.
