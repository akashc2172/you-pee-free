# Runtime Optimization Experiment Plan

Baseline: ~3 hours per solve. Goal: reduce runtime without breaking outputs.

## Metrics to preserve after each experiment

| Metric | Source | Tolerance |
|---|---|---|
| q_in / q_out | results CSV | ±2% |
| delta_p | results CSV | ±1.0 Pa |
| centerline pressure profile | QC plots | visual match |
| q_sh_prox / q_sh_mid / q_sh_dist | results CSV | ±5% |
| mesh_min_quality | results CSV | ≥ 0.05 |
| mass_imbalance | results CSV | ≤ 0.01 |
| solver convergence | log | must converge |

## Experiment 1: Coarser baseline mesh (safest first)

**What**: Increase global max element size by ~1.5×.

**How**: In Mesh → Size, increase `Maximum element size`. Example: if current max is 0.3mm, try 0.45mm.

**Expected**: 30-50% runtime reduction, because element count scales roughly as size^(-3) in 3D.

**Risk**: Low. Mesh quality gates in the QC pipeline will catch degradation.

**Comparison**: Run the same baseline `design_0000` with old and new mesh, diff the metrics table above.

## Experiment 2: Loosen solver tolerance

**What**: Change relative tolerance from 1e-4 to 5e-4 (halfway to 1e-3).

**How**: In Study → Solver Configuration → Stationary Solver, change `Relative tolerance`.

**Expected**: 20-40% fewer iterations. Final-step values should be very close to tighter tolerance.

**Risk**: Medium. If the flow field has marginal convergence regions, this might shift values. Compare q_sh_* carefully.

**Comparison**: Same design, same mesh, diff all metrics above.

## Experiment 3: Reduce continuation steps

**What**: If baseline uses 3+ p_ramp steps (e.g. 0.1, 0.5, 1.0), try (0.5, 1.0) or direct solve at p_ramp=1.0.

**How**: In Study → Continuation, reduce the number of parameter values.

**Expected**: Linear reduction in solve time proportional to steps removed.

**Risk**: Medium-high. Continuation is there to help convergence. If the direct solve fails to converge, revert.

**Comparison**: Check convergence first. Then diff all metrics above.

## What NOT to touch yet

- Domain geometry (kidney/ureter/bladder dimensions)
- Physics model (stay laminar, steady-state)
- Boundary condition values (490 Pa)
- Named selections or export structure
- Shaft-hole flux extraction layer

## Testing order

1. Run Experiment 1 first (lowest risk, highest expected payoff).
2. If Experiment 1 passes, run Experiment 2 on top of it.
3. Only try Experiment 3 if the combined result of 1+2 still needs more speedup.
4. Never stack all three untested changes at once.

## Recording results

For each experiment, record in a row:

```
experiment, mesh_max_mm, solver_tol, continuation_steps, runtime_s, q_out, q_in, delta_p, q_sh_prox, q_sh_mid, q_sh_dist, mesh_min_quality, mass_imbalance, converged
```

Compare against the baseline row.
