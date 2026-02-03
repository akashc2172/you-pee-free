# Experiment Run Log Template

## Purpose

Track all COMSOL simulations, LHS batches, and surrogate training iterations. Mirrors the "Run Log" sheet in `stent_comsol_tracker.xlsx`.

---

## Single Run Entry Template

Copy this template for each COMSOL run:

```markdown
### Run [ID]: [YYYYMMDD]_[batch]_[sample#]

**Basic Info**
- Run ID: 
- Date: 
- Git commit hash: 
- COMSOL model version: 
- Operator: 

**Parameters (Sampled)**
| Parameter | Value | Unit |
|-----------|-------|------|
| OD |  | mm |
| ID |  | mm |
| L_total |  | mm |
| L_prox |  | mm |
| L_mid |  | mm |
| L_dist |  | mm |
| r_t |  | - |
| r_sh |  | - |
| r_end |  | - |
| n_sh_prox |  | count |
| n_sh_mid |  | count |
| n_sh_dist |  | count |
| pitch_ratio |  | - |
| alpha |  | - |

**Derived Parameters**
| Parameter | Value | Unit |
|-----------|-------|------|
| wall_thickness |  | mm |
| d_sh |  | mm |
| pitch_min |  | mm |
| buffer |  | mm |

**Status**
- [ ] CAD generated
- [ ] Mesh created
- [ ] Solver converged
- [ ] Post-processed
- [ ] Validated

**Results (if converged)**
| Metric | Value | Unit |
|--------|-------|------|
| ΔP |  | Pa |
| Q_total |  | mL/min |
| Q_sh_prox |  | mL/min |
| Q_sh_mid |  | mL/min |
| Q_sh_dist |  | mL/min |
| CV_Qsh |  | - |
| WSS_avg |  | Pa |
| WSS_max |  | Pa |

**Diagnostics**
- Mass imbalance: %
- Iteration count: 
- CPU time: min
- Mesh quality (min): 

**Notes**
- 
- 

**Issues/Anomalies**
- 
```

---

## Batch-Level Summary Template

Use for each LHS batch (after all runs complete):

```markdown
## Batch [ID]: LHS_[n]_v[version]

**Sampling Info**
- Batch ID: LHS_60_v1
- Date range: YYYY-MM-DD to YYYY-MM-DD
- Target samples: 60
- Oversample factor: 3×
- Raw LHS samples: 180
- Feasible designs: [XX] (XX%)
- Successful COMSOL runs: [XX] (XX%)
- Git commit: [hash]
- LHS seed: [integer for reproducibility]

**Parameter Ranges (Actual)**
| Parameter | Min | Max | Unit |
|-----------|-----|-----|------|
| OD |  |  | mm |
| ID |  |  | mm |
| ... |  |  |  |

**Feasibility Filter Stats**
| Constraint | Rejected | % of Raw |
|------------|----------|----------|
| ID < 0.6 mm |  |  |
| L_mid < 10 mm |  |  |
| Hole packing (prox) |  |  |
| Hole packing (mid) |  |  |
| Hole packing (dist) |  |  |
| Other |  |  |

**Run Status Summary**
| Status | Count | % |
|--------|-------|---|
| Converged successfully |  |  |
| Mesh failure |  |  |
| Solver divergence |  |  |
| Post-processing error |  |  |
| Pending |  |  |

**Notes**
- 
```

---

## Surrogate Training Log Template

Track each surrogate model iteration:

```markdown
## Surrogate Model [ID]: GP_[kernel]_[date]

**Training Info**
- Model ID: GP_matern52_20250126
- Date: 
- Git commit: 
- Training data: Batch [IDs] (n = XXX)
- Features: 14 parameters → 12 effective (post-constraints)
- Targets: [list metrics]

**GP Configuration**
| Hyperparameter | Setting |
|----------------|---------|
| Kernel | Matérn 5/2 |
| ARD | Yes |
| Noise variance | [fitted value] |
| Mean function | Constant / Linear |
| Optimizer | L-BFGS-B |

**Validation (Blocked Holdout)**
| Metric | Train RMSE | Test RMSE | R² | Comment |
|--------|-----------|-----------|-----|---------|
| ΔP |  |  |  |  |
| Q_total |  |  |  |  |
| Q_sh_prox |  |  |  |  |
| Q_sh_mid |  |  |  |  |
| Q_sh_dist |  |  |  |  |

**Diagnostics**
- Length-scales (ARD): [list or note outliers]
- Noise estimate: 
- Marginal log-likelihood: 
- Optimization converged: Yes/No
- # restarts needed: 

**Calibration Check**
- [ ] P-P plot generated
- [ ] Calibration curve reviewed
- [ ] Uncertainty reliability: [Pass/Review/Fail]

**Decision**
- [ ] Surrogate accepted for optimization
- [ ] Needs more data (adaptive sampling)
- [ ] Retrain with different config

**Next Actions**
- 
```

---

## Quick Reference: File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| CAD files | `{run_id}.step` | `LHS60_v1_001.step` |
| COMSOL models | `{run_id}.mph` | `LHS60_v1_001.mph` |
| Result exports | `{run_id}_results.txt` | `LHS60_v1_001_results.txt` |
| Batch summaries | `batch_{id}_summary.md` | `batch_LHS60_v1_summary.md` |
| Surrogate logs | `gp_{kernel}_{date}.md` | `gp_matern52_20250126.md` |

---

## Spreadsheet Sync

Ensure this log stays in sync with `stent_comsol_tracker.xlsx`:
- **"Stent Tracker"** tab: Parameter columns + output columns
- **"Run Log"** tab: High-level status for all runs
- **This markdown file**: Detailed notes, issues, diagnostics

Recommended workflow:
1. Generate LHS batch → add to spreadsheet
2. Run COMSOL → update spreadsheet status column
3. Add detailed notes here for any issues/observations
4. After batch complete, copy summary to both locations
