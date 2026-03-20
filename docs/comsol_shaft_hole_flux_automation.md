# COMSOL Shaft-Hole Flux Automation

This is the baseline automation layer for per-hole shaft flux extraction.

Scope for this pass:
- shaft holes only
- metadata-driven local extraction targets
- grouped regional outputs preserved
- Python post-processing and plotting added

## Audit summary

Already correct before this pass:
- hole sidecar export existed
- canonical frame and grouped metadata existed
- grouped regional flux outputs remained the baseline science path

Missing before this pass:
- no repository-level shaft-hole extraction target contract
- no runner support for forwarding the `.holes.json` path into COMSOL
- no stable per-hole naming layer
- no parser/post-processor for exported per-hole flux values
- no plotting script for `axial_x_mm` vs signed/abs per-hole flux

## Naming contract

For each shaft hole:
- cut plane: `CP_<hole_id>`
- signed derived value: `DV_hole_<hole_id>_signed`
- abs derived value: `DV_hole_<hole_id>_abs`

Examples:
- `CP_shaft_mid_001`
- `DV_hole_shaft_mid_001_signed`
- `DV_hole_shaft_mid_001_abs`

## Metadata-driven inputs

The shaft-hole target builder consumes:
- `hole_id`
- `center_mm`
- `normal`
- `axial_x_mm`
- `axial_rank`
- `region`
- `type`

Only `type == shaft` is used in this pass.

## Files/scripts

Target builder:
- [build_shaft_hole_flux_targets.py](/Users/akashc/masters/scripts/build_shaft_hole_flux_targets.py)

Python utilities:
- [hole_flux.py](/Users/akashc/masters/src/comsol/hole_flux.py)

Plotter:
- [plot_shaft_hole_flux.py](/Users/akashc/masters/scripts/plot_shaft_hole_flux.py)

COMSOL model-method source:
- [BuildShaftHoleFluxLayer.java.txt](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer.java.txt)

Install/run guide:
- [comsol_shaft_hole_flux_method_install.md](/Users/akashc/masters/docs/comsol_shaft_hole_flux_method_install.md)

## Runner integration

The runner now forwards:
- `cad_path`
- `hole_metadata_path`

into the COMSOL batch parameter list.

That makes the sidecar path available to a COMSOL model method or Java-side automation without hand editing per design.

## COMSOL-side expectation

The `.mph` baseline template should consume `hole_metadata_path` and build shaft-hole local datasets from the sidecar.

Two execution paths are available:
- **Application Builder Method**: [BuildShaftHoleFluxLayer.java.txt](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer.java.txt)
- **Java Shell (no compilation)**: [BuildShaftHoleFluxLayer_shell.java](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer_shell.java)

Preferred strategy:
- local cut plane per shaft hole
- local masked patch around the hole center
- one signed and one absolute integration per hole

Fallback if the template cannot emit metadata columns directly:
- export stable `DV_hole_<hole_id>_signed` / `DV_hole_<hole_id>_abs` fields
- join back to the sidecar in Python

## Baseline test checklist on the current COMSOL file

1. Confirm your baseline `.mph` accepts `hole_metadata_path`.
2. Use the existing `design_0000.holes.json`.
3. Build shaft targets:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/build_shaft_hole_flux_targets.py \
  --holes_json /absolute/path/to/design_0000.holes.json
```

4. In COMSOL, automate creation of:
- `CP_shaft_*`
- `DV_hole_shaft_*_signed`
- `DV_hole_shaft_*_abs`

5. Export the per-hole flux table/CSV.

6. Plot in Python:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/plot_shaft_hole_flux.py \
  --holes_json /absolute/path/to/design_0000.holes.json \
  --flux_csv /absolute/path/to/per_hole_flux.csv \
  --output_dir /absolute/path/to/output_dir
```

Outputs:
- merged CSV with `hole_id`, `axial_x_mm`, `region`, `type`, `p_ramp`, `signed_flux_m3s`, `abs_flux_m3s`
- abs-flux plot
- signed-flux plot

## What stays unchanged

This does not remove or replace:
- `q_sh_prox`
- `q_sh_mid`
- `q_sh_dist`

Those grouped metrics remain the robust baseline outputs.
