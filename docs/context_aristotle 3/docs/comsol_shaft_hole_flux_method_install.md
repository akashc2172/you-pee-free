# COMSOL Shaft-Hole Flux Model Method

This is the actual COMSOL-side automation source for the baseline shaft-hole local flux layer.

Source file:
- [BuildShaftHoleFluxLayer.java.txt](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer.java.txt)

It matches the repository-side contract already in:
- [hole_flux.py](/Users/akashc/masters/src/comsol/hole_flux.py)
- [build_shaft_hole_flux_targets.py](/Users/akashc/masters/scripts/build_shaft_hole_flux_targets.py)
- [plot_shaft_hole_flux.py](/Users/akashc/masters/scripts/plot_shaft_hole_flux.py)

## What it does

Using `hole_metadata_path`, the method:

1. reads the `.holes.json`
2. filters to `type == "shaft"`
3. creates one cut plane per shaft hole:
   - `CP_<hole_id>`
4. creates two numerical derived values per shaft hole:
   - `DV_hole_<hole_id>_signed`
   - `DV_hole_<hole_id>_abs`
5. evaluates them after the solve
6. writes a tall CSV next to the sidecar:
   - `<design_id>_shaft_hole_flux.csv`

CSV columns:
- `hole_id`
- `axial_x_mm`
- `region`
- `type`
- `p_ramp`
- `signed_flux_m3s`
- `abs_flux_m3s`

This does not remove or replace the grouped outputs:
- `q_sh_prox`
- `q_sh_mid`
- `q_sh_dist`

## Placement in COMSOL

For COMSOL 6.1:

1. Open the baseline `.mph`.
2. Go to `Home -> Windows -> Application Builder`.
3. Under `Methods`, create a new method named:
   - `BuildShaftHoleFluxLayer`
4. Open:
   - [BuildShaftHoleFluxLayer.java.txt](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer.java.txt)
5. Paste the full contents into the method body.
6. Save the model.

Recommended usage:
- solve first
- run the method after the baseline continuation solve has completed

This is a postprocessing/build-results method, not a geometry-generation method.

## Runtime/model parameters expected

Required:
- `hole_metadata_path`
- `design_id`

Expected baseline defaults:
- solution dataset prefers `dset2`, then `dset1`
- solver tag prefers the dataset's linked solution, otherwise falls back to `sol1`
- velocity components are assumed to be `u`, `v`, `w`

If your baseline template uses different result dataset or velocity variable names, edit the constants at the top of the method source before pasting.

## Node naming

Per shaft hole:
- dataset:
  - `CP_<hole_id>`
- signed numerical:
  - `DV_hole_<hole_id>_signed`
- absolute numerical:
  - `DV_hole_<hole_id>_abs`

Example:
- `CP_shaft_mid_001`
- `DV_hole_shaft_mid_001_signed`
- `DV_hole_shaft_mid_001_abs`

These names intentionally match the Python parser contract in:
- [hole_flux.py](/Users/akashc/masters/src/comsol/hole_flux.py)

## Extraction logic

The method uses the validated masked local cut-plane idea:

- cut plane centered at sidecar `center_mm`
- cut plane normal from sidecar `normal`
- integrand based on local normal flux
- local masking by a spherical/disk patch using the sidecar radius

Signed expression:
- local `(n dot u)`

Absolute expression:
- `abs(n dot u)`

Mask:
- `if((x-x0)^2 + (y-y0)^2 + (z-z0)^2 <= r^2, 1, 0)`

## Important note on the current sidecar

For the current baseline sidecar, shaft-hole `center_mm` is the canonical axial station anchor used by the validated local masked workflow. It is not yet a true reconstructed hole-mouth centroid on the cylinder surface.

That means this method is aligned to your current baseline validation workflow. If you later upgrade the sidecar to emit true mouth centroids, the method can consume those directly without changing the naming contract.

## Smoke test for the current baseline `design_0000`

Use one of:
- [campaign_len140 design_0000.holes.json](/Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.holes.json)
- [campaign_len220 design_0000.holes.json](/Users/akashc/masters/data/campaigns/campaign_len220/cad/design_0000.holes.json)

Checklist:

1. In the solved baseline model, confirm the parameters are set:
   - `hole_metadata_path`
   - `design_id`
2. Run `BuildShaftHoleFluxLayer`.
3. Under `Results -> Datasets`, confirm new nodes like:
   - `CP_shaft_mid_001`
4. Under `Results -> Derived Values`, confirm new nodes like:
   - `DV_hole_shaft_mid_001_signed`
   - `DV_hole_shaft_mid_001_abs`
5. Confirm the CSV exists next to the sidecar:
   - `design_0000_shaft_hole_flux.csv`
6. Plot it with:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/plot_shaft_hole_flux.py \
  --holes_json /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.holes.json \
  --flux_csv /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000_shaft_hole_flux.csv \
  --output_dir /Users/akashc/masters/data/campaigns/campaign_len140/cad/shaft_hole_flux_debug
```

## Interactive testing note

If you test interactively inside COMSOL rather than through batch, string-like parameters may need to be entered with quotes in the Parameters table, for example:

- `hole_metadata_path = "/absolute/path/to/design_0000.holes.json"`
- `design_id = "design_0000"`

## Java Shell execution path (no Application Builder needed)

If you cannot or do not want to use the Application Builder, use the Java Shell version instead:

Source file:
- [BuildShaftHoleFluxLayer_shell.java](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer_shell.java)

Steps:

1. Open the solved baseline `.mph` in COMSOL 6.1.
2. Set the model parameters:
   - `hole_metadata_path = "/absolute/path/to/design_0000.holes.json"`
   - `design_id = "design_0000"`
3. Open `Home → Windows → Java Shell`.
4. Open `BuildShaftHoleFluxLayer_shell.java` in a text editor.
5. Select all, copy, and paste into the Java Shell editor pane.
6. Press Enter or click Run.

Output is identical to the Application Builder version:
- Cut planes: `CP_shaft_*` under Results → Datasets
- Derived values: `DV_hole_shaft_*_signed` / `DV_hole_shaft_*_abs` under Results → Derived Values
- CSV file: `<design_id>_shaft_hole_flux.csv` next to the sidecar

The Java Shell version is functionally identical to the Application Builder method. It uses procedural code with parallel arrays instead of inner classes because the Java Shell does not support class definitions.

## Manual fallback if the method editor is blocked

If you cannot run the method yet, use the already-generated target files:

- [design_0000.shaft_hole_flux_targets.csv](/Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.shaft_hole_flux_targets.csv)
- [design_0000.shaft_hole_flux_targets.json](/Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.shaft_hole_flux_targets.json)

These contain the exact:
- hole IDs
- cut plane names
- derived value names
- center coordinates
- normals
- mask radii

That gives you a copy-safe manual fallback without re-deriving tags by hand.
