# GP/BO Surrogate Decisions (Decisions 1-8)

This document captures the 8 computational decisions in the GP/BO pipeline, their rationale, and criteria for switching choices.

## Decision 1: Objective Framing

| Aspect | Detail |
|--------|--------|
| **Options** | A) Single objective (e.g., minimize ΔP) <br> B) Scalarization (weighted sum) <br> C) True multi-objective Pareto (ΔP vs Q_out vs side-hole flux) |
| **Current Choice** | Start single or scalarization to validate loop; graduate to Pareto once calibration is trusted |
| **Rationale** | • Reduces failure modes early <br> • Avoids premature Pareto before uncertainty is calibrated <br> • Simpler debugging |
| **Switch Trigger** | Single-objective surrogate achieves target accuracy on holdout; validation diagnostics show reliable uncertainty estimates |
| **Validation Metric** | Holdout RMSE/MAE within tolerance; calibration curves (predicted vs observed error) |

---

## Decision 2: Data Preprocessing & Transforms

| Aspect | Detail |
|--------|--------|
| **Options** | **Input normalization**: [0,1] scaling vs z-score (mean=0, std=1) <br> **Output transforms**: None vs log for ΔP/flux vs Box-Cox |
| **Current Choice** | Normalize all inputs to [0,1]; consider log transforms for ΔP/flux if spanning orders of magnitude |
| **Rationale** | • Kernel distance depends on scaling <br> • Transforms stabilize GP assumptions (homoscedastic noise, stationarity) <br> • [0,1] preserves interpretability of length-scale hyperparameters |
| **Switch Trigger** | If variance heteroscedasticity detected in residuals; if output spans >2 orders of magnitude |
| **Validation Metric** | Residual plots vs fitted values; Q-Q plots of standardized residuals |

---

## Decision 3: Sampling Plan

| Aspect | Detail |
|--------|--------|
| **Options** | A) Pure LHS (space-filling only) <br> B) LHS → adaptive BO (our plan) <br> C) BO from the start |
| **Config** | `default_samples`: 60; `oversample_factor`: 3-4× |
| **Current Choice** | Initial LHS + feasibility filtering (3× oversample, all dimensions normalized ∈[0,1]); then adaptive sampling via EI/UCB |
| **Rationale** | • Space-filling baseline ensures coverage <br> • Reduces invalid designs before GP sees data <br> • Supports stable GP initialization <br> • Sequential approach respects COMSOL runtime constraints |
| **Switch Trigger** | Feasible rate <50% → increase oversample; surrogate accuracy plateaus → activate adaptive sampling |
| **Validation Metric** | Feasible design rate; space-filling coverage metrics (minimax, maximin distances) |

---

## Decision 4: Surrogate Model Selection

| Aspect | Detail |
|--------|--------|
| **Options** | GP/Kriging vs Random Forest vs Neural Network vs Polynomial Chaos |
| **Current Choice** | **GP/Kriging** as primary surrogate |
| **Rationale** | • Naturally provides uncertainty estimates crucial for BO <br> • Works well with small datasets (<200 points) <br> • Analytical derivatives available <br> • Strong theoretical foundation for sequential design |
| **Switch Trigger** | If GP training unstable or scaling issues with >500 points → consider scalable approximations (SVGP) |
| **Validation Metric** | Training stability; predictive accuracy; uncertainty calibration |

---

## Decision 5: GP Specifics (Kernel + ARD + Noise)

| Aspect | Detail |
|--------|--------|
| **Kernel Options** | RBF/Squared Exp vs Matérn 5/2 vs Matérn 3/2 |
| **Length-scale Options** | ARD (Automatic Relevance Determination) vs single shared |
| **Noise Options** | Interpolating (noise=0) vs nonzero noise term |
| **Current Choice** | **Matérn 5/2** + ARD length-scales + small nonzero noise |
| **Rationale** | • Matérn 5/2: smooth-but-not-too-smooth (twice differentiable), avoids overconfidence <br> • RBF can oversmooth; Matérn 3/2 too rough for flow physics <br> • ARD → interpretability (identifies important dimensions) <br> • Noise handles solver/mesh jitter; avoids overfitting deterministic-ish data |
| **Switch Trigger** | Underfit → try Matérn 3/2 or additive kernel (prox/middle/distal sections semi-independent); overfit → increase noise |
| **Validation Metric** | Length-scale magnitudes; noise variance estimate; cross-validation log-likelihood |

---

## Decision 6: Training Procedure

| Aspect | Detail |
|--------|--------|
| **Options** | A) Maximize marginal likelihood (MLE) — standard <br> B) MAP priors if fits unstable <br> C) Fully Bayesian inference (MCMC over hyperparams) |
| **Current Choice** | **Marginal likelihood fitting** first; Bayesian priors later only if needed |
| **Rationale** | • Stable, fast iteration <br> • Defensible precedent for engineering BO <br> • Can upgrade to full Bayes if instability detected |
| **Switch Trigger** | Optimization fails to converge; length-scale estimates physically unreasonable; strong prior knowledge available |
| **Validation Metric** | Optimization convergence; hyperparameter magnitudes; sensitivity to restarts |

---

## Decision 7: Validation Strategy

| Aspect | Detail |
|--------|--------|
| **Options** | Random holdout vs blocked holdout vs leave-one-out vs sequential validation |
| **Current Choice** | **Blocked holdout** (respects sequential design structure) |
| **Rationale** | • Random holdout optimistic for sequential designs (future points correlated with training) <br> • Blocked: hold out entire contiguous batches <br> • Respects that LHS batches are designed together <br> • Prevents information leakage from adaptive sampling |
| **Switch Trigger** | If batch structure unclear; if need statistical efficiency → LOO-CV |
| **Validation Metric** | Holdout RMSE, MAE, R²; calibration metrics (P-P plots, CRPS); stability across different holdout blocks |

---

## Decision 8: Acquisition Function

| Aspect | Detail |
|--------|--------|
| **Single-objective Options** | EI / qEI (Expected Improvement) vs UCB/LCB (exploration-controlled) |
| **Multi-objective Options** | EHVI (Expected Hypervolume Improvement) vs qNEHVI (batch Pareto) |
| **Current Choice** | **EI/qEI early**; **EHVI/qNEHVI** once multi-objective enabled and calibration solid |
| **Rationale** | • Stable early loop with well-tested acquisition <br> • Scalable to batch selection <br> • Natural transition to Pareto later <br> • qEI allows parallel COMSOL runs |
| **Switch Trigger** | Single-objective converged; decision made to enable Pareto optimization; batch compute available |
| **Validation Metric** | Improvement over baseline; diversity of acquired points; Pareto front quality (hypervolume) |

---

## Summary Table

| Decision | Choice | Alternative | Switch Trigger |
|----------|--------|-------------|----------------|
| 1. Objective | Single/Scalarization → Pareto | Start with Pareto | Calibration trusted |
| 2. Transforms | [0,1] inputs; log outputs if needed | z-score; no transform | Heteroscedasticity detected |
| 3. Sampling | LHS 3× oversample → adaptive BO | Pure BO from start | Feasible rate <50% or accuracy plateau |
| 4. Model | GP/Kriging | RF, NN, PCE | >500 points or instability |
| 5. Kernel | Matérn 5/2 + ARD + noise | RBF, Matérn 3/2, additive | Under/overfit detected |
| 6. Training | Marginal likelihood | MAP, full Bayes | Convergence failure |
| 7. Validation | Blocked holdout | Random, LOO | Batch structure unclear |
| 8. Acquisition | EI/qEI → EHVI/qNEHVI | UCB throughout | Pareto enabled |

## Open Questions for Professor Review

1. What would you change first to make this GP-fit pipeline maximally defensible?
2. Kernel: Is Matérn 5/2 a good default here; when would you switch?
3. Noise: For deterministic-ish solvers, would you fit noise anyway? What replicate/mesh strategy?
4. Validation: What split strategy do you trust most for sequential design problems?
5. Multi-objective: When would you move from single/scalarization to true Pareto?
