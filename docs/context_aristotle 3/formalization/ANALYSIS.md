# Formalization Verification & Schema-Aligned Expansion — Analysis Report

## 1. Critique of the Initial Formalization

### Strengths

The Codex-generated formalization in `Stent/` is **remarkably well-scoped and mathematically sound**. Specific positives:

1. **All 27 theorems compile without `sorry`**. Every proof listed in the theorem inventory is fully machine-verified. No non-standard axioms are used (only `propext`, `Classical.choice`, `Quot.sound`).

2. **Clean separation of concerns**. The module layout (`Feature → FluxBookkeeping → Metrics → Objectives → Validity → WarmStart`) reflects a natural dependency order. Each module imports only what it needs.

3. **Appropriate abstraction level**. The README explicitly rejects formalizing COMSOL/PDE semantics, mesh generation, and exporter correctness — this is the right cut for a project where those components are still moving.

4. **Physically meaningful invariants**. Key theorems like `zoneAbsExchange_sum`, `classAbsExchange_sum`, `rawCentroid_mem_Icc`, and `exchangeSpread_eq_zero_of_commonCoord` encode real bookkeeping contracts that the pipeline depends on.

5. **Deterministic policy formalization**. The warm-start policy (`chooseBetter_tie_break`, `checkpointPolicy_total`) formalizes the exact selection logic including tie-breaking, which is critical for reproducibility.

### Weaknesses Identified

1. **Gap between `RawSample` and actual CSV schema**. The `Validity.lean` module defines `RawSample` and `ValidSample` in terms of `Option ℝ` fields, but never connects these to the actual output contract documented in `comsol_output_framework.md` (25 Tier 1 fields, 12 Tier 2 fields). There is no formal specification of what a valid CSV row looks like, or how per-feature rows relate to summary rows.

2. **`boundedLocalizationScore` is overly generic**. The `Metrics.lean` bounded localization wrapper `max 0 (min 1 (1 - spread/scale))` is correct but acknowledged as a placeholder. Its `hscale` hypothesis is unused in the proof (the theorem holds for any `scale > 0` but the proof doesn't actually need it). This is a sign the abstraction is not yet load-bearing.

3. **Minor linter warnings**. Several files have `simpa`-vs-`simp` warnings, unused `simp` arguments, and unused variable names. These are cosmetic but indicate the proofs were generated in one pass without cleanup.

4. **No cross-table invariants**. The formalization treats the per-feature flux list and the summary outputs as independent objects. There is no theorem stating that the zone-disaggregated totals in the summary must equal the corresponding zone-filtered sums from the per-feature table — the core bookkeeping invariant the pipeline actually depends on.

5. **`AggregateOutputs` is disconnected from the schema**. The `AggregateOutputs` structure has 5 fields (`pressureDrop`, `qOut`, `exchangeTotal`, `centroid`, `spread`), while the actual design-level CSV has 25+ fields. The mapping from one to the other is not formalized.

---

## 2. Cut or Modified Abstractions

### `boundedLocalizationScore` — retained but downgraded

The generic bounded localization wrapper in `Metrics.lean` was **retained as-is** because:
- It compiles and its theorem (`boundedLocalizationScore_mem_Icc`) is correct.
- Removing it would break the theorem inventory contract.
- The README already flags it as a placeholder for a future project-specific IQS formula.

The only change was renaming the unused `hscale` parameter to `_hscale` to silence the linter warning. This makes it clear the theorem holds trivially (clamping to [0,1] doesn't depend on the scale being positive) — a correct observation that the README already acknowledges.

### Minor linter fixes applied

- `Metrics.lean`: `hscale → _hscale`, removed unused `hne` simp argument, `simpa → simp`.
- These changes do not affect proof semantics.

---

## 3. Proposed Schema-Aligned Theorem Layer Design

The new `Stent/Schema.lean` module bridges the mathematical core to the empirical CSV contract. It introduces:

### Structures

| Structure | Purpose | Aligns with |
|---|---|---|
| `FeatureFluxRow` | One row of `feature_flux_long.csv` | Section 12B of `comsol_output_framework.md` |
| `DesignSummaryRow` | One row of `design_outputs.csv` | Tier 1 + Tier 2 outputs (Sections 2–3) |
| `QCConfig` | Pipeline QC gate configuration | Tier 2 diagnostics (Section 3) |

### Predicates

| Predicate | What it asserts |
|---|---|
| `FeatureFluxRow.isConsistent` | `absFlux = |signedFlux|`, area ≥ 0, normalizedX ∈ [0,1] |
| `DesignSummaryRow.deltaPConsistent` | `deltaP = p_in - p_out` |
| `DesignSummaryRow.conductanceConsistent` | `conductance = Q_out / deltaP` |
| `DesignSummaryRow.pathwayPartitionConsistent` | `fracLumen = Q_lumen/Q_out`, `fracAnnulus = Q_annulus/Q_out` |
| `DesignSummaryRow.unroofFractionConsistent` | `fracUnroof = Q_unroof_abs / Q_out` |
| `DesignSummaryRow.zoneHoleSumConsistent` | `prox + mid + dist = qHolesAbs` |
| `DesignSummaryRow.exchangeTotalConsistent` | `exchangeTotal = qHolesAbs + qUnroofAbs` |
| `DesignSummaryRow.tier1Consistent` | Conjunction of all Tier 1 consistency conditions |
| `crossTableZoneConsistent` | Summary zone totals match per-feature zone-filtered sums |
| `crossTableNetFluxConsistent` | Summary net hole flux matches sum of signed fluxes |
| `DesignSummaryRow.passesQC` | Solver converged ∧ mass balance within tolerance |

### Key Theorems (all fully proved)

| Theorem | Statement |
|---|---|
| `FeatureFluxRow.absFlux_nonneg_of_consistent` | Consistent rows have nonneg absFlux |
| `FeatureFluxRow.toFeatureFlux_absFlux_of_consistent` | Conversion preserves abs flux |
| `DesignSummaryRow.toRawSample_coreFields` | Summary → RawSample has all core fields |
| `DesignSummaryRow.toRawSample_valid` | QC-passing summary → ValidSample (bridges Schema ↔ Validity) |
| `DesignSummaryRow.derivedOutputs_isSome` | QC-passing summary → derived outputs computable |
| `DesignSummaryRow.derivedOutputs_pressureDrop` | Derived outputs match the schema pressure drop |
| `DesignSummaryRow.derivedOutputs_deltaP_eq` | ∃ agg with pressureDrop = deltaP |
| `featureRows_totalAbsExchange` | totalAbsExchange of converted rows = sum of absFlux fields |
| `crossTable_proxHoleAbsFlux_nonneg` | Cross-table consistency → proximal total ≥ 0 |
| `crossTable_midHoleAbsFlux_nonneg` | Cross-table consistency → middle total ≥ 0 |
| `crossTable_distHoleAbsFlux_nonneg` | Cross-table consistency → distal total ≥ 0 |

---

## 4. Formal Specification

The complete Lean 4 code is in `Stent/Schema.lean` (≈325 lines). All theorems compile without `sorry` and use only standard axioms (`propext`, `Classical.choice`, `Quot.sound`).

The module is imported via `Stent.lean`:

```lean
import Stent.Schema
```

### Architecture diagram

```
comsol_output_framework.md (25 Tier 1 + 12 Tier 2 fields)
        │
        ▼
 DesignSummaryRow ──────── tier1Consistent (6 sub-predicates)
        │                         │
        │  toRawSample            │ crossTableConsistent
        ▼                         ▼
   RawSample ◀──── FeatureFluxRow list
        │               │
  ValidSample            │ featureRows_totalAbsExchange
        │               │
  derivedOutputs?        ▼
        │          totalAbsExchange (FluxBookkeeping.lean)
        ▼
 AggregateOutputs ──── canonicalPhysicalObjective (Objectives.lean)
```

---

## 5. Conclusion & Future Extensions

### What was accomplished

1. **Verified**: All 27 original theorems compile without `sorry`. No non-standard axioms. Minor linter warnings cleaned up.

2. **Expanded**: Added `Stent/Schema.lean` with 11 new fully-proved theorems, 3 new structures, and 10 new predicates that formalize the CSV output contract from `comsol_output_framework.md`.

3. **Bridged**: The `toRawSample_valid` theorem connects the schema layer to the existing `Validity.lean` layer, establishing that a QC-passing `DesignSummaryRow` automatically yields a `ValidSample` — the gate for downstream optimization.

### Future extensions

1. **Pathway partition sum-to-one**: Prove that `fracLumenOut + fracAnnulusOut = 1` follows from the consistency predicates when `qLumenOut + qAnnulusOut = qOut`. This requires adding the flow conservation assumption as a hypothesis.

2. **Conductance positivity**: Prove `conductance > 0` under physically motivated assumptions (positive flow, positive pressure drop).

3. **Zone-complete partition theorem for feature rows**: Prove that for hole-class rows, the prox/mid/dist zone filter is exhaustive (analogous to `zoneAbsExchange_sum` in `FluxBookkeeping.lean`).

4. **Surrogate-target transform contracts**: Add a thin theorem layer over the monotone/bounded transforms (log, unit-normalize) used in GP surrogate training, connecting `Transform.unitNormalize_mem_Icc` to the actual surrogate feature columns.

5. **Tighter schema typing**: Replace `ℝ` fields that represent counts or flags with `ℕ` or `Bool` where appropriate (e.g., `nActiveHoles : Nat` is already done; `solverConverged : Bool` is done).

6. **CSV parser verification**: If/when the Python exporter is frozen, add a thin specification of the expected CSV column order and types, and prove that the `DesignSummaryRow` structure is isomorphic to it.
