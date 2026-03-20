# Hole Metadata Sidecar Spec

This document describes the production geometry-selection contract for hole-aware COMSOL extraction.

The production path is:
- export STEP geometry
- export matching `.holes.json` sidecar in the exact same canonical frame
- build COMSOL hole selections from metadata

The fallback path is:
- metadata-derived region boxes

Hand-guessed coordinate boxes are no longer the intended primary logic.

## Production goals

The sidecar is the authoritative source for:
- hole identity
- region grouping
- shaft vs coil typing
- canonical hole coordinates
- canonical hole normals
- axial ordering for plotting
- metadata-derived COMSOL helper selections

This is designed so later analysis can treat the stent itself as the `x` axis and support:
- discrete per-hole flux curves
- continuous axial flux curves
- hole overlays on continuous curves

## How the sidecar is produced

The generator now writes the sidecar automatically whenever STEP export happens:

```python
gen = StentGenerator(params)
gen.export_step(Path("data/my_run/design_0000.step"))
```

That creates:

```text
data/my_run/
  design_0000.step
  design_0000.holes.json
```

You can still call `export_hole_metadata(...)` directly when needed, but `export_step(...)` is now the normal path.

## Canonical export frame

The sidecar and STEP geometry share the same rigid canonical export frame:
- straight body axis aligned to `+X`
- body start at `x = 0`
- units = `mm`

This is critical. If the sidecar frame drifts from the STEP frame, axial flux plots become scientifically invalid.

## What is verified in code

Before metadata is written, the generator validates:
- total exported hole count matches realized generator hole count
- shaft-hole axial coordinates match realized shaft-hole positions within tolerance
- shaft-hole centers remain on the body centerline within tolerance
- normals are unit-length
- exported `axial_x_mm` matches exported `center_mm[0]`
- exported hole centers remain inside the canonical bounding box within tolerance

Current generator consistency tolerance:
- `0.1 mm`

## Sidecar schema

Top-level fields:
- `schema_version`
- `design_id`
- `frame_definition`
- `stent_length_mm`
- `od_mm`
- `id_mm`
- `r_outer_mm`
- `selection_margin_mm`
- `export_body_start_x_mm`
- `export_body_end_x_mm`
- `export_bbox_min_x_mm`
- `export_bbox_max_x_mm`
- `grouped_flux_regions`
- `holes`
- `axial_order`
- `selection_helpers`
- `analysis_support`
- `validation`

### `frame_definition`

```json
{
  "name": "canonical_stent_export_frame",
  "body_axis": "+X",
  "body_axis_vector": [1.0, 0.0, 0.0],
  "body_start_at_x_mm": 0.0,
  "units": "mm"
}
```

### `holes`

Each hole entry contains:
- `hole_id`
- `region`
- `type`
- `center_mm`
- `radius_mm`
- `normal`
- `axial_x_mm`
- `axial_rank`

Also preserved for backward compatibility:
- `id`
- `center`
- `hole_radius`
- `normal_vector`
- `selection_sphere_radius_mm`
- `selection_cylinder_radius_mm`
- `slab_half_width_x_mm`
- `arc_deg`

Example:

```json
{
  "hole_id": "shaft_mid_002",
  "region": "mid",
  "type": "shaft",
  "center_mm": [72.5, 0.0, 0.0],
  "radius_mm": 0.198,
  "normal": [0.0, 1.0, 0.0],
  "axial_x_mm": 72.5,
  "axial_rank": 6
}
```

## Shaft vs coil grouping

Type is explicit and preserved:
- `shaft`
- `coil`

This is intentional so later COMSOL/analysis can support:
- shaft-only grouped flux
- coil-only grouped flux
- combined grouped flux

## Axial ordering

Every hole receives:
- `axial_x_mm`
- `axial_rank`

Ordering rule:
- sort by canonical `x`
- tie-break by `type` with shaft before coil
- final tie-break by `hole_id`

This makes hole ordering stable and plotting-safe.

The sidecar also includes:
- `axial_order`

which is the plotting-ready ordered list of:
- `hole_id`
- `axial_x_mm`
- `axial_rank`
- `region`
- `type`

## Selection helpers

Two metadata-driven COMSOL strategies are supported.

### Strategy A: preferred

Per-hole local selections:
- small spheres or cylinders around each hole
- unioned by region or by region+type

This is the preferred production path because it is closest to the true hole geometry.

### Strategy B: MVP fallback

Metadata-derived region boxes:
- tight `x` bounds from actual hole coordinates
- small padding based on hole radius and outer diameter
- `y/z` span derived from actual hole coordinates plus OD-based padding

This is still metadata-driven and far safer than guessed boxes.

The sidecar exposes:
- `selection_helpers.per_hole_local_selections`
- `selection_helpers.region_selection_boxes`
- `selection_helpers.typed_region_selection_boxes`

`region_selection_boxes` is also preserved as a top-level compatibility alias.

## COMSOL consumption plan

Recommended:
1. read `cad_path`
2. derive `cad_path.with_suffix(".holes.json")`
3. build local per-hole selections from `selection_helpers.per_hole_local_selections`
4. union by:
   - `prox`
   - `mid`
   - `dist`
5. optionally also union by:
   - `prox + shaft`
   - `prox + coil`
   - etc.

Fallback:
1. read `selection_helpers.region_selection_boxes`
2. create `sel_holes_prox`, `sel_holes_mid`, `sel_holes_dist`

## Analysis support

The sidecar includes future-ready plotting helpers:
- `analysis_support.discrete_per_hole_flux_template`
- `analysis_support.continuous_axial_profile_support`

These do not contain solved flux values yet. They define the stable x-axis contract for later COMSOL outputs:
- one point per hole
- continuous axial curves
- hole overlay markers

## Campaign integration

The campaign generation path now ensures every exported STEP has a matching sidecar.

Manifests now include:
- `hole_metadata_file`
- `hole_metadata_schema_version`
- `hole_metadata_hole_count`
- `hole_metadata_units`

So no design should exist in a campaign CAD batch without a metadata sidecar.
