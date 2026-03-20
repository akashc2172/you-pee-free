# COMSOL Hole Selection Setup

Use the hole metadata sidecar as the production path:
- [hole_metadata_sidecar_spec.md](/Users/akashc/masters/docs/hole_metadata_sidecar_spec.md)

This file explains the COMSOL-side interpretation.

## Production path

Preferred:
1. read `design_XXXX.holes.json`
2. build one local selection per hole
3. union by region and, when needed, by region+type

Fallback:
1. read `selection_helpers.region_selection_boxes`
2. build `sel_holes_prox`, `sel_holes_mid`, `sel_holes_dist`

Do not use hand-guessed coordinate ranges as the primary logic anymore.

## Strategy A: per-hole local selections

This is the preferred option.

For each hole entry in `holes` or `selection_helpers.per_hole_local_selections`:
- create a local sphere or cylinder selection
- center it at `center_mm`
- use the metadata-provided local radius
- create boundary-level selections

Then union the members into:
- `sel_holes_prox`
- `sel_holes_mid`
- `sel_holes_dist`

If later needed, also union by:
- `prox + shaft`
- `prox + coil`
- `mid + shaft`
- `dist + coil`

## Strategy B: metadata-derived region boxes

This is the MVP fallback.

Use:
- `selection_helpers.region_selection_boxes.prox`
- `selection_helpers.region_selection_boxes.mid`
- `selection_helpers.region_selection_boxes.dist`

These boxes are derived from actual hole coordinates, not guessed manually.

Create:
- `sel_holes_prox`
- `sel_holes_mid`
- `sel_holes_dist`

at boundary level.

## Derived values

Once selections exist, add:

- `DV_Sci_Flux_Holes_Prox`
- `DV_Sci_Flux_Holes_Mid`
- `DV_Sci_Flux_Holes_Dist`

using:

```text
u*nx+v*ny+w*nz
```

or the equivalent COMSOL Laminar Flow normal volumetric flux expression.

Recommended CSV output names:
- `q_sh_prox`
- `q_sh_mid`
- `q_sh_dist`

Optional WSS outputs:
- `wss_max`
- `wss_p95_global`
- `wss_p99_global`

## Downstream behavior

Python now computes grouped science metrics from the grouped hole outputs:
- `q_sh_total_signed`
- `q_sh_total_abs`
- `hole_uniformity_cv_grouped`
- `hole_uniformity_maxmin_grouped`
- `fraction_partition_lumen`
- `fraction_partition_holes`

So COMSOL should export the raw grouped fluxes, not the derived algebra.
