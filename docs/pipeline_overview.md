# Stent GP/BO Pipeline Overview

## 1. Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STENT OPTIMIZATION PIPELINE                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   INPUT      │     │    LHS SAMPLING  │     │  FEASIBILITY     │
│   Space      │────▶│   (space-filling)│────▶│   FILTERING      │
│  (11 dims)   │     │   oversample 3×  │     │  (hard constraints)│
└──────────────┘     └──────────────────┘     └────────┬─────────┘
                                                      │
                              ┌───────────────────────┘
                              ▼
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   COMSOL     │     │   SURROGATE      │     │   VALIDATION     │
│  CFD Sims    │────▶│   GP/Kriging     │────▶│   (blocked       │
│              │     │   training       │     │    holdout)      │
└──────────────┘     └────────┬─────────┘     └────────┬─────────┘
                              │                        │
                              ▼                        │
                     ┌──────────────────┐              │
                     │   ACQUISITION    │              │
                     │  EI/UCB → EHVI   │──────────────┘
                     │  (adaptive)      │    if not converged
                     └────────┬─────────┘
                              ▼
                     ┌──────────────────┐
                     │  OPTIMIZATION    │
                     │ Single objective │
                     │ → Multi-obj Pareto│
                     └──────────────────┘
```

## 2. Phase Summary

| Phase | Input | Output | Tooling |
|-------|-------|--------|---------|
| **1. Design Space** | Parameter ranges (11 dimensions) | LHS samples (normalized [0,1]) | `scipy.stats.qmc` |
| **2. Feasibility** | Raw LHS samples | Valid CAD parameters | `build123d` geometry checks |
| **3. CAD Generation** | Valid parameters | `.step` + optional quality-gated `.stl` files | `build123d` scripted + STL mesh QA |
| **4. CFD Simulation** | CAD geometry | Flow metrics | COMSOL Multiphysics |
| **5. Surrogate Training** | (X, y) pairs | GP model | `scikit-learn`, `GPy`, or `BoTorch` |
| **6. Validation** | Held-out test set | Error metrics | Custom diagnostics |
| **7. Adaptive Sampling** | GP uncertainty | New candidate points | EI/UCB acquisition |
| **8. Optimization** | Trained surrogate | Optimal designs | Bayesian Optimization |

## 3. Key Loop: Iterative Surrogate Improvement

```
Initial LHS batch (e.g., 60 samples, 3× oversample → ~180 → ~60 valid)
                    │
                    ▼
           COMSOL simulations
                    │
                    ▼
           Train GP surrogate
                    │
                    ▼
           Validate on 20% holdout
                    │
            ┌───────┴───────┐
            │               │
        Accurate?       Not accurate?
            │               │
            ▼               ▼
    Use surrogate    Adaptive sampling
    for optimization   (EI/UCB) → new batch
                            │
                            └──────► (loop back to COMSOL)
```

## 4. Decision Points

See [`decisions_gp_surrogate.md`](decisions_gp_surrogate.md) for detailed rationale on each choice.

1. **Objective framing**: Start single/scalarization → graduate to Pareto
2. **Transforms**: Input [0,1] scaling; log transforms for ΔP/flux if needed
3. **Sampling**: LHS + feasibility filtering → adaptive BO
4. **Surrogate**: GP/Kriging with Matérn 5/2 kernel + ARD
5. **Training**: Marginal likelihood (MLE), MAP fallback
6. **Validation**: Blocked holdout for sequential designs
7. **Acquisition**: EI/qEI early → EHVI/qNEHVI for multi-objective

## 5. Data Flow

### Parameter Schema → See [`parameter_schema.md`](parameter_schema.md)
- 11 sampled dimensions (coil geometry fixed for this campaign stage)
- Constraints: ID_min, gap_min, buffer zones, section lengths
- For unroofed designs, body-hole features are tracked as `requested` and `realized`; training prefers realized hole counts when available.

### Metrics → See [`metrics_catalog.md`](metrics_catalog.md)
- Pressure drop (ΔP)
- Total output flow (Q_total)
- Side hole flux distribution
- Run trust/QC diagnostics: mass balance, mesh quality, convergence status

### Logging → See [`experiment_log.md`](experiment_log.md)
- Git hash for code version
- COMSOL template + simulation contract version
- Parameter values
- Run status (`valid | invalid_qc | failed_solver | failed_geometry | failed_extraction`)

## 6. Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Surrogate accuracy | RMSE < threshold per metric | Holdout validation |
| Feasible design rate | >60% post-filtering | LHS batch stats |
| Coverage | Space-filling in valid region | Minimax distance |
| Calibration | Reliable uncertainty estimates | P-P plots, CRPS |

## 7. Current Status

- ✅ Proposal drafted (intro + methods + partial supplement)
- ✅ LHS script written
- ✅ Stent tracker with 36 parameter columns + 4 tabs
- ⏳ Review with Parnian (COMSOL feasibility/throughput)
- ⏳ Review with professor (GP/BO pipeline defensibility)
- ⏳ Model script implementation
- ⏳ Begin COMSOL runs

## 8. File Locations

| Artifact | Location |
|----------|----------|
| Proposal | `stent_optimization_proposal_012226.docx` |
| Decision deck | `gpr_sampling_meeting.pptx` |
| Tracker | `stent_comsol_tracker.xlsx` |
| This pipeline doc | `docs/pipeline_overview.md` |
| GP decisions | `docs/decisions_gp_surrogate.md` |
| Parameters | `docs/parameter_schema.md` |
| Metrics | `docs/metrics_catalog.md` |
| Experiment log | `docs/experiment_log.md` |
