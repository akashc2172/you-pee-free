# COMSOL Normalized Frame Reference

Use this note when rebuilding the first real COMSOL template against the generator-normalized STEP exports.

## Generator assumptions

- Exported stent axis is aligned to global `+x`.
- Straight body start is anchored at `x = 0`.
- Straight body centerline is centered at `y = 0`, `z = 0`.
- The body-center metadata is derived from measured straight-shaft cross-sections on the final generated solid, not only from the path bookkeeping.
- STEP export uses the normalized solid directly; no hidden COMSOL-only rotate/translate step is required after import.
- The proximal coil may extend into negative `x`.

## Current manual template reference

Reference values are in [`config/comsol_dumbbell_reference.yaml`](/Users/akashc/masters/config/comsol_dumbbell_reference.yaml).

The original helper-estimated reservoir placements were not sufficient to fully cover the coils in COMSOL. The current manually validated template values are therefore the ground-truth reference until they are replaced by a programmatic generator.

Current working template values:

- `kidney_reservoir_radius_mm = 18.0`
- `kidney_reservoir_length_mm = 31.0`
- kidney cylinder origin: `x = -25`, `y = 0`, `z = 0`
- `ureter_tube_radius_mm = 4.0`
- ureter cylinder origin: `x = 0`, `y = 0`, `z = 0`
- `ureter_tube_length_rule = span x = export_body_start_x to x = export_body_end_x`
- `bladder_reservoir_radius_mm = 18.0`
- `bladder_reservoir_length_mm = 31.0`
- bladder cylinder origin: `x = 264`, `y = 0`, `z = 0`

Why these values currently win:

- They fully cover the coils in the current normalized export frame.
- They produce a usable manual COMSOL template without additional geometry nudging.
- They are the reference values to copy unless and until a programmatic template generator replaces them.

Build all three primitives along the global `x` axis.

## Current selection-box guidance

Use these as the current manual validated coordinate boxes instead of the earlier idealized estimates:

- `inlet`
  - cap box: `x = [-25.5, -24.5]`, `y = [-18, 18]`, `z = [-18, 18]`
- `outlet`
  - cap box: `x = [294.5, 295.5]`, `y = [-18, 18]`, `z = [-18, 18]`
- `coil_zone`
  - build as the union of two boxes:
  - proximal coil box: `x = [export_bbox_min_x, export_body_start_x]`, `y = [-18, 18]`, `z = [-18, 18]`
  - distal coil box: `x = [export_body_end_x, export_bbox_max_x]`, `y = [-18, 18]`, `z = [-18, 18]`
- `mid_zone`
  - `x = [export_body_start_x + 0.25 * (export_body_end_x - export_body_start_x), export_body_start_x + 0.75 * (export_body_end_x - export_body_start_x)]`
  - `y = [-4, 4]`
  - `z = [-4, 4]`

## Length-stratum note

Template construction is currently manual once per length/template, while batch execution is automated afterward.

For the planned fixed-length workflow:

- `campaign_len140` should use a length-specific manual template such as `base_flow_len140_v1.mph`
- `campaign_len220` should use a length-specific manual template such as `base_flow_len220_v1.mph`

The values above describe the currently validated manual template, not a universal automatic placement rule for every future length.

## Helper command

Use the generator-side helper to print the current template reference values and body-frame metadata before touching COMSOL:

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
- keep the manual validated kidney/bladder placements unless you are intentionally rebuilding a new length-specific template
- center the ureter tube on the straight shaft, not the whole-object bbox
- size `coil_zone` and `mid_zone` from the body-centered metadata (`export_body_start_x`, `export_body_end_x`, `export_bbox_min_x`, `export_bbox_max_x`, `export_body_center_y`, `export_body_center_z`)

Previously generated STEP files do not inherit this new frame automatically. Regenerate them before rebuilding the COMSOL template.
