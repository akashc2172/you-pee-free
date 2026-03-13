# COMSOL Normalized Frame Reference

Use this note when rebuilding the first real COMSOL template against the generator-normalized STEP exports.

## Generator assumptions

- Exported stent axis is aligned to global `+x`.
- Straight body start is anchored at `x = 0`.
- Straight body centerline is centered at `y = 0`, `z = 0`.
- The body-center metadata is derived from measured straight-shaft cross-sections on the final generated solid, not only from the path bookkeeping.
- STEP export uses the normalized solid directly; no hidden COMSOL-only rotate/translate step is required after import.
- The proximal coil may extend into negative `x`.

## Canonical dumbbell helper spec

Reference values are in [`config/comsol_dumbbell_reference.yaml`](/Users/akashc/masters/config/comsol_dumbbell_reference.yaml).

Recommended starting dimensions:

- `kidney_reservoir_radius_mm = 18.0`
- `kidney_reservoir_length_mm = 20.0`
- `ureter_tube_radius_mm = 4.0`
- `ureter_tube_length_rule = span x = export_body_start_x to x = export_body_end_x`
- `bladder_reservoir_radius_mm = 18.0`
- `bladder_reservoir_length_mm = 20.0`

Recommended placement in the normalized frame:

- Kidney reservoir spans `x = export_body_start_x - 20` to `x = export_body_start_x`
- Ureter tube spans `x = export_body_start_x` to `x = export_body_end_x`
- Bladder reservoir spans `x = export_body_end_x` to `x = export_body_end_x + 20`
- All three cylinders use `y = export_body_center_y` and `z = export_body_center_z`

Build all three primitives along the global `x` axis.

## Recommended COMSOL box selections

Use these as the first reproducible coordinate boxes instead of eyeballing:

- `inlet`
  - cap box: `x = [export_body_start_x - 20.5, export_body_start_x - 19.5]`, `y = [export_body_center_y - 18, export_body_center_y + 18]`, `z = [export_body_center_z - 18, export_body_center_z + 18]`
- `outlet`
  - cap box: `x = [export_body_end_x + 19.5, export_body_end_x + 20.5]`, `y = [export_body_center_y - 18, export_body_center_y + 18]`, `z = [export_body_center_z - 18, export_body_center_z + 18]`
- `coil_zone`
  - build as the union of two boxes:
  - proximal coil box: `x = [export_bbox_min_x, export_body_start_x]`, `y = [export_body_center_y - 18, export_body_center_y + 18]`, `z = [export_body_center_z - 18, export_body_center_z + 18]`
  - distal coil box: `x = [export_body_end_x, export_bbox_max_x]`, `y = [export_body_center_y - 18, export_body_center_y + 18]`, `z = [export_body_center_z - 18, export_body_center_z + 18]`
- `mid_zone`
  - `x = [export_body_start_x + 0.25 * (export_body_end_x - export_body_start_x), export_body_start_x + 0.75 * (export_body_end_x - export_body_start_x)]`
  - `y = [export_body_center_y - 4, export_body_center_y + 4]`
  - `z = [export_body_center_z - 4, export_body_center_z + 4]`

## Helper command

Use the generator-side helper to print the exact values for one design before touching COMSOL:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/print_comsol_template_values.py \
  --campaign <campaign_name> \
  --design_id <design_id>
```

## Template-prep note

Older setup instructions assumed the stent could arrive tilted. That is no longer the intended frame for newly generated STEP files.

When preparing `base_flow_v1.mph` from regenerated CAD:

- import the regenerated STEP
- assume the shaft is already aligned to `+x`
- assume the straight shaft starts at `x = 0`
- assume the straight shaft centerline is already at `y = 0`, `z = 0`
- build the dumbbell cylinders along the `x` axis
- center the ureter tube on the straight shaft, not the whole-object bbox
- size selections from the body-centered metadata (`export_body_start_x`, `export_body_end_x`, `export_bbox_min_x`, `export_bbox_max_x`, `export_body_center_y`, `export_body_center_z`)

Previously generated STEP files do not inherit this new frame automatically. Regenerate them before rebuilding the COMSOL template.
