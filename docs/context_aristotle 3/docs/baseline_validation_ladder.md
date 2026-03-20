## Baseline validation ladder (steady campaign)

Purpose: make the next empirical validation step **explicit**, **repeatable**, and hard to do wrong.
This is support infrastructure, not a full automation system.

### Scope

- **Steady laminar baseline** only
- **No Tier A / peristalsis**
- **No advanced WSS/OSI/RT** beyond optional spot checks

### Required smoke designs

- `design_0000` at **L=140 mm**
- `design_0000` at **L=220 mm**

### Mesh levels (minimum viable)

Run each smoke design at **2–3 mesh levels**:
- coarse
- medium
- (optional) fine

Record the mesh “level” you used (template variant or `mesh_retry_level` policy) so comparisons are traceable.

### Checks to run per mesh level

#### A) Sign + conservation sanity (hard gates)

- **Flow signs**: `Q_in_ml_min < 0 < Q_out_ml_min`
- **Pressure signs**: `p_in_avg_Pa > p_out_avg_Pa` and `deltaP_Pa > 0`
- **Mass balance**: `mass_balance_relerr <= 0.01` (1%)

If any fail: treat as **fatal** for that run (do not use for surrogate).

#### B) Hole sign sanity (warning unless systematic)

- Check whether `invariant_warnings` contains `hole_flux_majority_negative`.
  - If it appears **consistently** across all meshes: likely a global normal/sign mismatch → fix extraction, not analysis.
  - If it appears sporadically: keep as warning; some reversed holes may be physical.

#### C) Partition-plane sanity (warning, but must be understood)

- Check `frac_lumen_out` and `frac_annulus_out` exist and are finite.
- Expect `frac_lumen_out + frac_annulus_out` to be “reasonable” (near 1 if the partition plane is clean and upstream of unroof).
- If `distal_partition_fractions_do_not_sum_to_one` appears:
  - verify the partition plane is upstream of the unroof in the CAD metadata
  - confirm the COMSOL template uses the intended measurement surface

#### D) Mesh stability of Tier‑1 surrogate descriptors (what you compare across meshes)

Compare across mesh levels:
- `deltaP_Pa`
- `Q_out_ml_min`
- `exchange_number` (Ex)
- `hole_only_exchange_number` (Ex_h)
- `net_direction_index` (NDI)
- `hole_flux_centroid_norm`
- `hole_flux_iqs_norm`
- `n_active_holes`

Goal: Ex / NDI / centroid / IQS should be **at least as stable** as raw per-hole fluxes.

### What counts as “fatal” vs “non-fatal” right now

#### Fatal (do not train on these)

- `run_status != valid`
- Non-finite (`NaN/inf`) in `deltaP_Pa` or `Q_out_ml_min`
- `mass_balance_relerr > 0.01`
- Systematic sign inconsistency (`Q_in` / `Q_out` / `ΔP` sign rules violated)

#### Non-fatal (log + investigate)

- `hole_flux_majority_negative` (unless systematic)
- `distal_partition_fractions_do_not_sum_to_one` (must be explained; may indicate partition-plane placement or template mismatch)
- `missing_stent_length_for_normalization` (fix your scalars export so `stent_length_mm` is included)

### After the ladder passes

Only after A–D look sane for both lengths:
- launch the first full LHS batch (e.g., 60 valid designs)
- train the surrogate on Tier‑1 **transformed** outputs only

