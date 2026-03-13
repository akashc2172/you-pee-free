# Real COMSOL Smoke-Run Checklist

This checklist is for the first real COMSOL validation ladder:
- `1-run` smoke
- `5-run` mini-batch
- `20-run` pilot

Use this file together with:
- [`config/comsol_template_contract.schema.json`](/Users/akashc/masters/config/comsol_template_contract.schema.json)
- [`config/base_flow_v1.contract.example.json`](/Users/akashc/masters/config/base_flow_v1.contract.example.json)
- [`docs/comsol_normalized_frame_reference.md`](/Users/akashc/masters/docs/comsol_normalized_frame_reference.md)
- [`src/comsol/expectations.py`](/Users/akashc/masters/src/comsol/expectations.py)

## Before the first run

Check the `.mph` template:
- The template exists at a stable path, for example `data/comsol_templates/base_flow_v1.mph`.
- The template is a manually prepared COMSOL model. Python does not create it.
- The imported STEP should be regenerated from the normalized generator frame before template rebuild.
- Use `scripts/print_comsol_template_values.py` to get the body-centered cylinder and selection-box coordinates for the design you are templating.
- The physics contract is steady, incompressible, laminar, Newtonian flow.
- The pressure contract is `p_in = 490 Pa`, `p_out = 0 Pa`, `ΔP = 490 Pa`.
- The outer fluid region is the triple-domain dumbbell geometry.

Check the named selections in COMSOL:
- `inlet`
- `outlet`
- `stent_walls`
- `coil_zone`
- `mid_zone`

Check the sidecar contract file:
- The file exists adjacent to the template as `<base_mph_stem>.contract.json`.
- Its contents match [`config/base_flow_v1.contract.example.json`](/Users/akashc/masters/config/base_flow_v1.contract.example.json).
- `schema_version = comsol_template_contract_v1`
- `parser_expectations_version = comsol_parser_expectations_v1`
- `sim_contract_version = v1_deltaP490_steady_laminar`
- `domain_template = triple_domain_dumbbell`
- `selection_strategy = coordinate_bbox`
- `pressure_contract.mode = pressure_driven`
- `pressure_contract.p_inlet_pa = 490.0`
- `pressure_contract.p_outlet_pa = 0.0`
- `pressure_contract.delta_p_pa = 490.0`

Check the export nodes in COMSOL:
- One export must produce `{run_id}_results.csv`.
- One export must produce `{run_id}_realized_geometry.csv`.
- The batch log must land at `{run_id}.log`.

## What the parser expects

The source of truth is [`src/comsol/expectations.py`](/Users/akashc/masters/src/comsol/expectations.py).

Accepted result CSV aliases:
- `q_out`: `q_out`, `q_total`, `spf_out1_volumeflowrate`, `outlet_volume_flow_rate`
- `q_in`: `q_in`, `spf_inl1_volumeflowrate`, `inlet_volume_flow_rate`
- `p_in`: `p_in`, `p_inlet`, `spf_inl1_paverage`, `inlet_average_pressure`
- `p_out`: `p_out`, `p_outlet`, `spf_out1_paverage`, `outlet_average_pressure`
- `delta_p`: `delta_p`, `dp`, `pressure_drop`
- `mass_imbalance`: `mass_imbalance`, `mass_balance_error`
- `mesh_min_quality`: `minimum_element_quality`, `mesh_min_quality`, `min_element_quality`
- `solver_relative_tolerance`: `solver_relative_tolerance`, `relative_tolerance`, `solver_tol`

Accepted convergence log patterns:
- `Stationary Solver.*Ended at`
- `Solver finished.`
- `Study completed successfully`

Accepted tolerance log patterns:
- `Relative tolerance(?: used)?: ...`

Required artifact names:
- `{run_id}_results.csv`
- `{run_id}_realized_geometry.csv`
- `{run_id}.log`

Required QC evidence:
- explicit convergence evidence
- explicit solver tolerance evidence
- finite `q_in`, `q_out`, `p_in`, `p_out`, `delta_p`
- `ΔP = 490 Pa +/- 1.0 Pa`
- `q_in < 0 < q_out`
- `p_in > p_out` and positive `delta_p`
- mass balance `< 1%`
- mesh quality `> 0.05`

## Run the 1-run smoke command

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/debug_comsol_smoke_run.py \
  --base_mph /absolute/path/to/base_flow_v1.mph \
  --cad_file /absolute/path/to/design_0000.step \
  --output_dir /absolute/path/to/smoke_runs \
  --design_id design_0000 \
  --comsol_exec comsol
```

Equivalent CLI wrapper:

```bash
PYTHONPATH=/Users/akashc/masters python3 src/cli.py debug-comsol-smoke \
  --base_mph /absolute/path/to/base_flow_v1.mph \
  --cad_file /absolute/path/to/design_0000.step \
  --output_dir /absolute/path/to/smoke_runs \
  --design_id design_0000 \
  --comsol_exec comsol
```

## What should appear in `attempt_0/`

Inside `<output_dir>/<design_id>/attempt_0/`, check for:
- `<design_id>.mph`
- `<design_id>.log`
- `stdout.log`
- `stderr.log`
- `<design_id>_results.csv`
- `<design_id>_realized_geometry.csv`

Inside `<output_dir>/<design_id>/`, also check for:
- `<design_id>_provenance.json`
- `<design_id>_result.json`
- `<design_id>_compatibility_report.json`

## Manual inspection after the first run

Open the compatibility report and confirm:
- template contract is marked valid
- all expected artifacts exist
- `run_status` is reported
- `failure_class` is reported when non-valid
- `found_raw_metric_keys` shows the columns that actually appeared in the result CSV

Open the result CSV and log manually:
- confirm the flow/pressure column names match one of the accepted aliases
- confirm the log contains one accepted convergence line
- confirm the log contains one accepted relative-tolerance line
- confirm the realized geometry CSV actually contains `realized_*` columns
- confirm `delta_p` is near 490 Pa
- confirm `q_in` is negative and `q_out` is positive
- confirm mass balance is below 0.01
- confirm mesh quality is above 0.05

## Next-run decision tree

If the sidecar contract is missing or invalid:
- Fix `<base_mph_stem>.contract.json` first.
- Re-run the single-run smoke command before touching the batch runner.

If expected files are missing from `attempt_0/`:
- Fix the COMSOL export nodes or batch log/output paths in the template.
- Re-run the single-run smoke command.

If the parser cannot find result CSV columns:
- Compare the actual CSV headers against [`src/comsol/expectations.py`](/Users/akashc/masters/src/comsol/expectations.py).
- If COMSOL is exporting a stable alternate header, add that alias in code before moving on.
- Do not start the 5-run batch until the single-run CSV parses cleanly.

If the log does not match convergence or tolerance patterns:
- Compare the actual log wording against the accepted regex patterns in [`src/comsol/expectations.py`](/Users/akashc/masters/src/comsol/expectations.py).
- If the log is valid but worded differently, add the new pattern in code and rerun the smoke test.
- If the log truly lacks the evidence, fix the template/solver output settings first.

If selections are wrong or empty in COMSOL:
- Fix the template manually in COMSOL.
- Update the sidecar only after the template is actually corrected.
- Re-run the single-run smoke command before testing 5 runs.

If parsing works but QC fails:
- Treat that as a real simulation/template issue, not a parser issue.
- Inspect mesh quality, pressure/flow signs, and `delta_p` first.
- Only move to the 5-run batch after one design reaches `run_status = valid`.

If the 1-run smoke is valid:
- Run 5 designs with the same template and confirm no manual reselection.
- If all 5 produce valid or clearly classified non-valid terminal states without parser confusion, move to the 20-run pilot.
