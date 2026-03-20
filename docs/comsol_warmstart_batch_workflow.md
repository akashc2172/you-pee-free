# COMSOL Two-Machine Warm-Start Batch Workflow

This workflow is split on purpose:

- The Mac decides the run plan.
- The COMSOL PC executes the run plan.

No Python is required on the COMSOL PC.

## Scope

This is a nearest-neighbor warm-start workflow for a 60-design batch with:

- one reusable template `.mph` per length bucket
- one Mac-side anchor bank
- one Mac-side `jobs_manifest.csv`
- one COMSOL-side master runner method that consumes exactly one manifest row per run

For your current plan:

- `design_0000` is the first cold/full-sweep warmup anchor for its length bucket
- yes, you should keep two warm-start pools if you have two fixed-length templates

## Length Buckets

Do not warm-start across template lengths.

Use either:

- two files:
  - `anchor_bank_len140.csv`
  - `anchor_bank_len220.csv`

or one file with a required `template_id` column.

The scaffold here uses one file with `template_id` values:

- `len140`
- `len220`

The selector only scores a design against anchors from the same `template_id`.

## Folder Layout

Recommended Windows layout:

```text
C:\akashcomsoltest\
  jobs\
    jobs_manifest.csv
    run_status.csv
  inputs\
    design_0100\
      design_0100.step
      design_0100.holes.json
      design_0100.meters.json
    design_0101\
      ...
  anchors\
    design_0000\
      p075.mphbin
      p090.mphbin
      p095.mphbin
    design_0002\
      p075.mphbin
      p090.mphbin
  out\
    design_0100\
      design_0100_flux_scalars.csv
      design_0100_flux_features.csv
      design_0100.log
```

The Mac can stage files into this shape. The COMSOL PC should only need the manifest, the template, and a batch command that names a manifest row index.

## `anchor_bank.csv` Schema

Use [`anchor_bank.csv`](/Users/akashc/masters/examples/comsol_warmstart/anchor_bank.csv) as the template.

Required columns:

- `anchor_design_id`: solved design identifier
- `template_id`: length/template bucket such as `len140` or `len220`
- `family_label`: coarse family label used for a small mismatch penalty
- `topology_label`: hard topology class; mismatch forces cold
- `stent_length_mm`
- `hole_count_total`
- `hole_diameter_mm`
- `unroof_fraction`
- `prox_hole_count`
- `mid_hole_count`
- `dist_hole_count`
- `checkpoint_075_ready`
- `checkpoint_090_ready`
- `checkpoint_095_ready`
- `checkpoint_075_path`
- `checkpoint_090_path`
- `checkpoint_095_path`
- `solve_status`: only rows with `solved` are eligible anchors

Recommended extra columns:

- `notes`
- `last_solved_utc`
- `template_mph`

## Selector Policy

The Mac-side selector is [`warmstart_selector.py`](/Users/akashc/masters/scripts/warmstart_selector.py). The shared logic lives in [`warmstart.py`](/Users/akashc/masters/src/comsol/warmstart.py).

Distance definition:

- weighted normalized squared difference over:
  - `stent_length_mm`
  - `hole_count_total`
  - `hole_diameter_mm`
  - `unroof_fraction`
  - `prox_hole_count`
  - `mid_hole_count`
  - `dist_hole_count`
- plus a small `family_label` penalty
- plus a large `topology_label` penalty

Operational policy:

- `d <= 0.10` -> request `0.95` / `warm95`
- `0.10 < d <= 0.20` -> request `0.90` / `warm90`
- `0.20 < d <= 0.35` -> request `0.75` / `warm75`
- `d > 0.35` -> `cold`
- topology mismatch -> `cold` even if the numeric distance is small
- wrong `template_id` -> not even considered as an anchor candidate

Checkpoint fallback policy:

- if `warm95` is requested but the selected anchor lacks a `0.95` checkpoint, fall back to `0.90`
- if `0.90` is also missing, fall back to `0.75`
- if no requested checkpoint exists, emit `cold`

That fallback is intentional. It keeps the manifest executable without hand-editing the run plan.

## Example Metadata Inputs

Example selector inputs live in:

- [`design_0100.metadata.json`](/Users/akashc/masters/examples/comsol_warmstart/design_metadata/design_0100.metadata.json)
- [`design_0101.metadata.json`](/Users/akashc/masters/examples/comsol_warmstart/design_metadata/design_0101.metadata.json)
- [`design_0102.metadata.json`](/Users/akashc/masters/examples/comsol_warmstart/design_metadata/design_0102.metadata.json)
- [`design_0103.metadata.json`](/Users/akashc/masters/examples/comsol_warmstart/design_metadata/design_0103.metadata.json)

Each metadata file contains:

- the similarity features
- the `template_id`
- the future COMSOL paths that should land in the manifest:
  - `measurement_metadata_path`
  - `holes_path`
  - `step_path`

That means the selector does not need to rediscover file naming rules later.

## Example Manifest

Example output manifest:

- [`jobs_manifest.csv`](/Users/akashc/masters/examples/comsol_warmstart/jobs_manifest.csv)

Important columns:

- `design_id`
- `template_id`
- `measurement_metadata_path`
- `holes_path`
- `step_path`
- `anchor_design_id`
- `requested_start_checkpoint`
- `start_checkpoint`
- `schedule_type`
- `p_schedule`
- `anchor_checkpoint_path`
- `status`
- `selection_notes`

`requested_start_checkpoint` records the threshold outcome. `start_checkpoint` is the actual executable checkpoint after anchor availability fallback.

## COMSOL Runner Design

Use a single master runner method:

- [`RunManifestJob.java.txt`](/Users/akashc/masters/src/comsol/java/RunManifestJob.java.txt)

Method inputs:

- `jobs_manifest_path`
- `manifest_row_index`
- `run_status_log_path`

Execution contract:

1. Read the selected manifest row inside COMSOL.
2. Extract:
   - `design_id`
   - `template_id`
   - `step_path`
   - `holes_path`
   - `measurement_metadata_path`
   - `schedule_type`
   - `p_schedule`
   - `start_checkpoint`
   - `anchor_checkpoint_path`
3. Update the geometry import feature to point at `step_path`.
4. Update the Parametric Sweep `p_ramp` list from `p_schedule`.
5. Configure warm-start state:
   - cold: disable checkpoint loading
   - warm: load `anchor_checkpoint_path` and bind `start_checkpoint`
6. Rebuild:
   - `BuildShaftHoleFluxLayer`
   - `BuildCoilHoleFluxLayer`
   - `BuildFluxExtractionLayer`
7. Solve.
8. Export:
   - `<design_id>_flux_scalars.csv`
   - `<design_id>_flux_features.csv`
9. Append one line to `run_status.csv`.

## How Hard-Coded COMSOL Inputs Become Per-Run Values

Current pain point:

- `measurement_metadata_path` is hard-coded in a Method Call node
- `design_id` is hard-coded in a Method Call node

That must change to this pattern:

1. The manifest row becomes the source of truth.
2. The master runner reads the row.
3. The master runner owns the current run values:
   - `design_id`
   - `measurement_metadata_path`
   - `holes_path`
   - `step_path`
4. The master runner passes those values into the layer-build methods directly.

Result:

- no manual UI edit of `design_id`
- no manual UI edit of `measurement_metadata_path`
- no manual UI edit of the sweep list

## Should the Layer Methods Be Called Directly?

Yes.

Preferred structure:

- one static Method Call node, or one batch entry point, that triggers `RunManifestJob`
- inside `RunManifestJob`, call:
  - `BuildShaftHoleFluxLayer`
  - `BuildCoilHoleFluxLayer`
  - `BuildFluxExtractionLayer`

Why this is better than separate static Method Call nodes:

- the execution order is explicit
- the per-run file paths live in one place
- the run cannot accidentally reuse stale GUI values from the previous design
- warm-start setup and layer rebuild stay coupled to the same manifest row

The layer builders should behave like subroutines of the master runner, not as independent UI-configured jobs.

## Copy-Paste Readiness of the Layer Methods

Current recommendation:

- keep [`BuildFluxExtractionLayer.java.txt`](/Users/akashc/masters/src/comsol/java/BuildFluxExtractionLayer.java.txt) as-is if it is already working for you
- use [`BuildShaftHoleFluxLayer.java.txt`](/Users/akashc/masters/src/comsol/java/BuildShaftHoleFluxLayer.java.txt) and [`BuildCoilHoleFluxLayer.java.txt`](/Users/akashc/masters/src/comsol/java/BuildCoilHoleFluxLayer.java.txt) directly as the copy-paste sources

Why I am not rewriting those right now:

- they already follow the repo’s COMSOL-safe style
- they already contain copy-paste setup notes and self-discovery fallback
- the stronger need for this batch workflow is the new master runner and manifest contract

If you want, the next pass can be a targeted cleanup pass only on those two method files to make their install comments even tighter without changing the logic.

## What Must Be Parameterized Inside COMSOL

These values must stop being fixed literals in the template:

- CAD import filename: `step_path`
- hole metadata input: `holes_path`
- measurement metadata input: `measurement_metadata_path`
- design label used in exports: `design_id`
- parametric sweep list for `p_ramp`
- warm-start enable/disable flag
- warm-start checkpoint file path
- warm-start checkpoint target level
- export filenames for:
  - flux scalars CSV
  - flux features CSV
- run status log path

These COMSOL tags also need one-time verification in the template:

- geometry import feature tag
- study tag
- parametric sweep feature tag
- solver / initial value feature tag
- export node tags

## What Is Definitely Automatable Now

- Mac-side anchor selection from `anchor_bank.csv`
- length-bucket filtering via `template_id`
- weighted normalized distance computation
- topology mismatch cold-start gating
- checkpoint fallback from `0.95 -> 0.90 -> 0.75 -> cold`
- manifest generation
- storing all per-run paths and schedules in one CSV
- COMSOL-side manifest-row parsing in a Java/App Builder method
- COMSOL-side run status logging
- replacing hard-coded `design_id` and `measurement_metadata_path` with manifest-driven values
- moving layer rebuild ownership into one master runner method

## What Still Needs Live COMSOL Verification

- the exact API call that updates the imported STEP feature in your current template
- the exact API call that updates the Parametric Sweep node for `p_ramp`
- the exact solver feature that loads checkpoint files for warm starts
- the exact API or syntax COMSOL accepts for one method calling another in your current model
- the exact export node tags for writing `<design_id>_flux_scalars.csv` and `<design_id>_flux_features.csv`
- whether checkpoint files should be `.mph`, `.mphbin`, or another solver-specific artifact in your setup
- whether the layer methods should run before solve, after solve, or split into pre-solve build and post-solve export steps in the current template

## Suggested First Validation Sequence

1. Finish the full cold schedule on `design_0000` for its own template bucket.
2. Add `design_0000` to the anchor bank as the first solved full-sweep anchor.
3. Prove `RunManifestJob` can read row 1 and write one line to `run_status.csv`.
4. Prove it can swap `design_id` and `measurement_metadata_path` without any GUI edits.
5. Prove it can update `p_ramp` from the manifest.
6. Prove one cold job end to end.
7. Prove one warm job from `0.75`.
8. Prove one warm job from `0.90`.
9. Prove one warm job from `0.95`.
10. Only then launch the 60-design batch.
