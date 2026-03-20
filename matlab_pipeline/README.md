# MATLAB COMSOL One-Shot Pipeline

This folder adds a MATLAB-first orchestration path for COMSOL campaign runs.

It is designed for the current state of the project:

- a manually prepared base `.mph` template already exists
- CAD `.step` files and `.holes.json` sidecars already exist
- the shaft-hole postsolve layer is implemented in COMSOL as `BuildShaftHoleFluxLayer`
- the working COMSOL method currently consumes method-call string inputs:
  - `hole_metadata_path`
  - `design_id`

The pipeline does not depend on the Python runner. MATLAB becomes the top-level orchestrator.

One detail to be explicit about:

- the artifact/QC layer can check convergence and solver tolerance only if your COMSOL LiveLink session writes that information to the MATLAB console/diary
- if your LiveLink session does not echo those lines, set:
  - `qc.require_solver_tolerance = false`
  - `qc.require_convergence_evidence = false`
  in the config, or add a template-specific log capture step

## What it does

For each design in a manifest, the pipeline can:

1. open the base COMSOL model in MATLAB LiveLink
2. point the CAD import feature at the design STEP file
3. optionally set runtime model parameters
4. rebuild geometry and mesh
5. run the study
6. set shaft-hole method-call inputs
7. run the shaft-hole method call
8. export the main results CSV
9. export the realized-geometry CSV
10. save a solved model copy
11. copy the generated shaft-hole CSV into the attempt folder
12. apply MATLAB-side artifact/QC checks
13. write campaign checkpoint and result summaries

## Files

- `run_one_shot_campaign.m`
  - top-level campaign runner
- `run_one_shot_design.m`
  - one-design execution + artifact/QC handling
- `load_pipeline_config.m`
  - config loader with defaults and validation
- `example_config.json`
  - template/config example for the current COMSOL workflow

## Requirements

- MATLAB
- COMSOL with LiveLink for MATLAB
- a prepared base template `.mph`
- a matching `<base_mph>.contract.json` if you want to keep the repo contract discipline
- a manifest CSV with at least:
  - `design_id`
  - `cad_file`
- optionally:
  - `hole_metadata_file`

If `hole_metadata_file` is absent, the runner derives it as `cad_file` with suffix `.holes.json`.

## Usage

From MATLAB:

```matlab
addpath('/Users/akashc/masters/matlab_pipeline');
records = run_one_shot_campaign('/Users/akashc/masters/matlab_pipeline/example_config.json');
```

## Output layout

For each design:

- `<output_dir>/<design_id>/attempt_0/<design_id>.mph`
- `<output_dir>/<design_id>/attempt_0/<design_id>_results.csv`
- `<output_dir>/<design_id>/attempt_0/<design_id>_realized_geometry.csv`
- `<output_dir>/<design_id>/attempt_0/<design_id>_shaft_hole_flux.csv`
- `<output_dir>/<design_id>/attempt_0/<design_id>_matlab.log`
- `<output_dir>/<design_id>/<design_id>_result.json`

Campaign-level outputs:

- `<output_dir>/batch_checkpoint.csv`
- `<output_dir>/batch_results.csv`

## Important template assumptions

This pipeline is config-driven because COMSOL tags are template-specific.

The example config assumes tags like:

- `comp1`
- `geom1`
- `imp1`
- `mesh1`
- `std1`
- `methodcall1`

If your template uses different tags, edit `example_config.json`.

## Current method-call contract

This pipeline is set up for the currently working COMSOL method body that uses:

```java
String holeMetadataPath = hole_metadata_path;
String designId = design_id;
```

That means the runner treats shaft-hole inputs as method-call inputs, not CLI string parameters.

## Known boundary

This pipeline is intended to automate one-shot runs from MATLAB. It does not magically infer the correct import/export/method tags from an arbitrary `.mph`.

You still need one valid template configuration per template family. Once those tags are correct, the run path is automated.
