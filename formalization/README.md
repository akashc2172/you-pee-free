# Stent Lean Sidecar

This directory documents a deliberately scoped Lean/mathlib sidecar for the pediatric ureteral stent optimization pipeline.

## Scope Decision

This formalization covers the parts of the pipeline that are already mathematically stable enough to prove things about:

- feature and extraction metadata,
- finite flux bookkeeping over exported per-feature rows,
- aggregate output metrics built from those rows,
- QC predicates for whether a sample is admissible for optimization,
- weighted scalarized objectives over aggregate outputs,
- nearest-neighbor warm-start scoring and checkpoint policy logic.

This formalization does not attempt to verify:

- Navier-Stokes or reduced CFD physics,
- COMSOL API behavior,
- mesh generation,
- STEP geometry correctness,
- exporter code correctness,
- empirical optimality of the warm-start policy.

That cut is intentional. The real project already has stable mathematical contracts at the metrics and policy layer, but not yet a frozen enough solver or exporter contract to justify deeper formalization.

## Why This Scope Is Balanced

Potential overreach points that were rejected:

1. Formalizing PDE or COMSOL semantics would create fake depth relative to the actual project bottlenecks.
2. Freezing the current project-specific localization formula too early would overfit an evolving metric story.
3. Treating the warm-start score as a true metric would be mathematically misleading once topology/source mismatch penalties are included.

Potential weak points that were strengthened:

1. A purely symbolic objective would be too detached, so the library includes a canonical scalarization in addition to a generic term framework.
2. A flux-only formalization would miss QC gating, which is essential for method rigor.
3. A nearest-neighbor policy without deterministic tie-breaking would be incomplete for actual pipeline use.

Final balance:

- finite list-based definitions instead of abstract measure-theoretic machinery,
- exact proofs for invariants that matter in the appendix/methods layer,
- abstract interfaces only where the project formulas are still moving.

## Module Layout

- `Stent/Feature.lean`: feature metadata layer.
- `Stent/FluxBookkeeping.lean`: signed/absolute flux bookkeeping and subset sums.
- `Stent/Metrics.lean`: pressure drop, total exchange, centroid, spread, bounded localization wrapper.
- `Stent/Objectives.lean`: aggregate outputs, weighted objective terms, canonical scalarization, transform contracts.
- `Stent/Validity.lean`: QC predicate for admissible exported samples.
- `Stent/WarmStart/Distance.lean`: design-vector score for warm-start anchor selection.
- `Stent/WarmStart/Policy.lean`: deterministic nearest-anchor selection and checkpoint policy.
- `Stent/Examples.lean`: toy examples mirroring the stent pipeline at small scale.

## Theorem Inventory

| Theorem | Why it matters | Status | Dependencies / assumptions |
|---|---|---|---|
| `FeatureFlux.absFlux_nonneg` | Encodes physical nonnegativity of absolute exchange contributions | proved | none |
| `totalAbsExchange_nonneg` | Guarantees canonical exchange aggregate is nonnegative | proved | none |
| `totalAbsExchange_eq_zero_of_all_abs_zero` | Captures a basic bookkeeping sanity check | proved | every entry has zero absolute flux |
| `zoneAbsExchange_sum` | Shows zone totals recover the global total | proved | relies on `Zone = prox | mid | dist` as an exhaustive partition |
| `classAbsExchange_sum` | Same additivity for feature classes | proved | relies on the declared feature-class partition |
| `pressureDrop_nonneg_of_le` | Matches physical interpretation of `ΔP` when inlet pressure dominates outlet pressure | proved | `p_out ≤ p_in` |
| `rawCentroid_mem_Icc` | Ensures normalized centroid stays in `[0,1]` | proved | nonnegative weights, coordinates in `[0,1]`, positive total weight |
| `rawCentroid_perm` | Shows centroid is independent of feature ordering | proved | list permutation |
| `rawCentroid_eq_commonCoord` | Shows centroid collapses to the common active coordinate | proved | nonnegative weights, positive total weight, all positive-weight points share coordinate `c` |
| `exchangeSpread_nonneg` | Makes spread a mathematically legitimate localization statistic | proved | nonnegative weights, positive total weight |
| `exchangeSpread_perm` | Spread is invariant under feature reordering | proved | list permutation |
| `exchangeSpread_eq_zero_of_commonCoord` | Formalizes the “all exchange in one axial location” case | proved | same support-constancy assumptions as centroid theorem |
| `boundedLocalizationScore_mem_Icc` | Gives a safe bounded localization wrapper for downstream optimization | proved | positive scale |
| `Transform.unitNormalize_mem_Icc` | Formal contract for bounded metric normalization | proved | `lo < hi`, input metric in `[lo, hi]` |
| `ValidSample.coreFields` | Separates QC gating from optimization logic | proved | `ValidSample cfg sample` |
| `derivedOutputs?_isSome_of_valid` | Valid samples can be converted into objective-layer outputs | proved | `ValidSample cfg sample` |
| `score_nonneg` | Warm-start score is a nonnegative selection score | proved | nonnegative weights embedded in config |
| `score_symm` | Symmetry holds when the score components are symmetric | proved | current score definition |
| `score_self` | An identical solved anchor has zero score | proved | same design on both sides |
| `score_self_le` | Zero-score self-match is minimal among nonnegative scores | proved | score nonnegativity |
| `selectNearest?_isSome_of_nonempty` | Nearest-anchor selection is total on nonempty candidate sets | proved | nonempty anchor list |
| `selectNearest?_mem` | The chosen anchor actually comes from the provided solved set | proved | selection returns `some anchor` |
| `chooseBetter_tie_break` | Formalizes deterministic tie-breaking by anchor id | proved | equal scores, lower id on left |
| `checkpointPolicy_of_incompatible` | Topology mismatch deterministically forces reset | proved | incompatible topology flag |
| `checkpointPolicy_of_near` | Near anchors map to the high checkpoint class | proved | compatible topology, distance ≤ near threshold |
| `checkpointPolicy_of_medium` | Middle regime is well-defined | proved | compatible topology, `near < d ≤ medium` |
| `checkpointPolicy_of_far` | Far anchors fall back to cold start | proved | compatible topology, `medium < d` |
| `checkpointPolicy_total` | Policy covers all cases | proved | none |

## Scientifically Faithful Abstractions

### Formalized directly now

- per-feature signed and absolute flux,
- zone/class aggregates,
- pressure drop,
- total exchange magnitude,
- centroid and spread over normalized axial locations,
- QC gating as a predicate over exported sample fields,
- weighted scalarization over aggregate outputs,
- nearest-neighbor warm-start score and checkpoint thresholds.

### Abstracted on purpose

- exact COMSOL evaluation semantics,
- finiteness/NaN behavior inside the numerical solver,
- exact project-specific IQS formula,
- direct proof obligations for the Python/Java exporter.

The centroid/spread layer is the defensible abstraction for the current project state: it captures localization mathematically without pretending that the final project-specific IQS is already frozen.

## Future Work

- replace the generic bounded localization wrapper with the final project-specific localization score once frozen,
- add finite-set versions of the list theorems if the downstream data model moves to deduplicated maps,
- link the validity predicate more tightly to the evolving Python output schema,
- add a thin theorem layer over surrogate-target transforms used in GP training.

## Running

From the repository root:

```bash
lake build
```

The package exposes the root module:

```lean
import Stent
```
