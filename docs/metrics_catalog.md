# COMSOL Metrics Catalog

## Overview

This document defines the output metrics extracted from COMSOL CFD simulations. Metrics are categorized by priority: **Primary** (used for optimization), **Secondary** (exploratory/potential future metrics), and **Diagnostic** (for validation/debugging).

> ⚠️ **Status**: Metric definitions are preliminary. Final selection TBD with Parnian based on COMSOL feasibility and computational cost.

---

## Primary Metrics (Optimization Targets)

These metrics will be used directly in the optimization loop (single-objective or Pareto).

| Symbol | Name | Unit | COMSOL Expression | Objective | Rationale |
|--------|------|------|-------------------|-----------|-----------|
| **ΔP** | Pressure Drop | Pa | `pin - pout` | Minimize | Primary hemodynamic metric; lower is better for patient comfort |
| **Q_total** | Total Output Flow | mL/min | `∫(v·n)dA @ outlet` | Maximize | Ensure adequate drainage |
| **Q_sh_prox** | Proximal Side-Hole Flow | mL/min | `∫(v·n)dA @ prox_holes` | Maximize | Even distribution across sections |
| **Q_sh_mid** | Middle Side-Hole Flow | mL/min | `∫(v·n)dA @ mid_holes` | Maximize | Even distribution across sections |
| **Q_sh_dist** | Distal Side-Hole Flow | mL/min | `∫(v·n)dA @ dist_holes` | Maximize | Even distribution across sections |

### Flow Distribution Quality

| Symbol | Name | Unit | Definition | Objective |
|--------|------|------|------------|-----------|
| **CV_Qsh** | Coefficient of Variation (side-hole flows) | - | `std(Q_sh_prox, Q_sh_mid, Q_sh_dist) / mean(...)` | Minimize | Penalizes uneven distribution |
| **SHI** | Side-Hole Index | - | `Q_sh_total / Q_total` | [TBD] | Fraction through side vs end holes |

---

## Secondary Metrics (Exploratory)

These metrics may be monitored but not necessarily optimized initially. Can be elevated to primary based on sensitivity analysis.

| Symbol | Name | Unit | COMSOL Expression | Notes |
|--------|------|------|-------------------|-------|
| **WSS_avg** | Average Wall Shear Stress | Pa | `mean(μ∇v @ walls)` | Thrombosis risk indicator |
| **WSS_max** | Maximum Wall Shear Stress | Pa | `max(μ∇v @ walls)` | Localized high-shear zones |
| **OSI** | Oscillatory Shear Index | - | `[TBD formula]` | Recirculation indicator |
| **RT_avg** | Average Residence Time | s | `∫c dt / ∫c dt @ t→∞` | Particle clearance |
| **Energy_Loss** | Viscous Energy Loss | W or mW | `∫(μ|∇v|²)dV` | Efficiency metric |
| **J_Total** | Total Momentum Flux | kg·m/s² | `∫ρ(v·n)vdA` | Alternative flow characterization |

---

## Diagnostic Metrics (Validation/Debugging)

Used to verify simulation sanity and convergence.

| Symbol | Name | Purpose | Target |
|--------|------|---------|--------|
| **Mass_Imbalance** | Mass flow in - out | Conservation check | < 0.1% |
| **Iter_Count** | Solver iterations | Convergence behavior | Reasonable/stable |
| **CPU_Time** | Wall clock time | Resource planning | Track for scaling |
| **Mesh_Quality** | Minimum element quality | Mesh adequacy | > 0.1 (COMSOL metric) |

---

## Metric Extraction from COMSOL

### Boundary Integration Setup

```
Outlets:
├── End hole (outlet_end): Q_end = ∫(v·n)dA
├── Proximal side holes (outlet_sh_prox): Q_sh_prox = ∫(v·n)dA  
├── Middle side holes (outlet_sh_mid): Q_sh_mid = ∫(v·n)dA
└── Distal side holes (outlet_sh_dist): Q_sh_dist = ∫(v·n)dA

Q_total = Q_end + Q_sh_prox + Q_sh_mid + Q_sh_dist
Q_sh_total = Q_sh_prox + Q_sh_mid + Q_sh_dist

Pressure:
├── Inlet average: p_in = <p>@inlet
└── Outlet average: p_out = <p>@outlet_end
ΔP = p_in - p_out
```

### Velocity/Shear Post-Processing

```
Wall Shear Stress:
  τ_w = μ × (∂v/∂n) @ wall boundaries
  
Average WSS: τ_w_avg = ∫τ_w dA / ∫dA  (over all fluid-wetted walls)
Max WSS: τ_w_max = max(τ_w)
```

---

## Pareto Front Considerations

When moving to multi-objective optimization, candidate Pareto fronts:

1. **ΔP vs Q_total**: Classic flow resistance trade-off
2. **ΔP vs CV_Qsh**: Pressure drop vs flow uniformity
3. **ΔP vs Q_sh_total vs Q_end**: Side vs end flow distribution
4. **3D**: ΔP vs Q_total vs CV_Qsh (pressure, flow, uniformity)

---

## Open Questions for Parnian

- [ ] **Computational cost**: Which metrics are expensive to extract? Can we compute all 5 primary metrics per run without significant overhead?
- [ ] **Mesh dependency**: Do we need mesh refinement studies for WSS metrics, or can we rely on ΔP/Q which may be more robust?
- [ ] **Transient vs steady**: Are these steady-state metrics sufficient, or do we need time-averaged transient results?
- [ ] **Clinical relevance**: Which secondary metrics (WSS, OSI, RT) are worth the computational cost for your specific clinical hypotheses?
- [ ] **Failure modes**: What constitutes a "failed" simulation? (divergence, negative pressures, unrealistic velocities)

---

## Metric Ranges (Expected)

Based on literature and preliminary estimates (to be validated):

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| ΔP | 0 - 500 Pa | Highly design-dependent |
| Q_total | 50 - 500 mL/min | CSF drainage range |
| Q_sh_* (per section) | 10 - 150 mL/min | Section flow distribution |
| CV_Qsh | 0 - 0.5 | 0 = perfectly uniform |
| WSS_avg | 0.01 - 1 Pa | Low shear for CSF |
| WSS_max | 0.1 - 10 Pa | Watch for high-shear zones |

---

## References

- See `stent_comsol_tracker.xlsx` → "COMSOL Metrics Reference" tab
- Ishant's literature review (studies on CSF stent/VP shunt flow metrics)
- COMSOL documentation: Laminar Flow module, boundary integration
