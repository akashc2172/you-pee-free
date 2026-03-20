## Surrogate output schema (frozen, baseline steady campaign)

This repo treats `src/surrogate/output_schema.py` as the **single source of truth** for:
- Tier‑1 surrogate targets (and their transforms)
- Tier‑2 QC / gating fields
- Tier‑3 diagnostics (explicitly not optimized)

If docs and code disagree, **code wins** and docs should be updated to match.

### Tier‑1 surrogate targets (raw → transformed)

| Raw column | Meaning | Transformed column | Transform |
|---|---|---|---|
| `deltaP_Pa` | pressure drop | `log_deltaP` | `log(max(|ΔP|, eps))` |
| `Q_out_ml_min` | outlet flow | `log_Q_out` | `log(max(|Q_out|, eps))` |
| `exchange_number` | `Q_exchange_total_abs / Q_out` | `log_Ex` | `log(max(|Ex|, eps))` |
| `hole_flux_centroid_norm` | centroid / stent_length | `logit_centroid_norm` | `logit(clamp(centroid_norm))` |
| `hole_flux_iqs_norm` | IQS / stent_length | `logit_IQS` | `logit(clamp(IQS_norm))` |

`eps` defaults to `1e-6` (see `DEFAULT_EPS`).

### Tier‑1 optional (raw → transformed)

| Raw column | Transformed | Notes |
|---|---|---|
| `hole_flux_dominance_ratio` | `log_R_max` | single-hole dominance |
| `net_direction_index` | `atanh_NDI` | clamps to \((-1,1)\) before `atanh` |

### Tier‑2 QC / gating

These are **required for filtering** and provenance, but are **not** GP targets:
- `run_status` (must be `valid` for training)
- `mass_balance_relerr`
- `solver_converged_flag`
- `mesh_ndof`
- `n_active_holes`
- `invariant_warnings`
- `invariants_passed`

### Tier‑3 diagnostics (explicitly not optimized in baseline)

Examples:
- zone triplets (`prox/mid/dist` flux and fractions)
- `CV_Qsh`
- per-hole diagnostic columns (`Q_hole_*`, `absQ_hole_*`, `hole_active_*`)
- coil-specific outputs
- any WSS/OSI/RT metrics

