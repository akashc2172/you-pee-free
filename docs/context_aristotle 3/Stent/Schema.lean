/-
  Schema.lean — Schema-aligned theorem layer

  This module bridges the mathematical formalization (RawSample, AggregateOutputs,
  FeatureFlux, etc.) to the empirical CSV/summary output contract documented in
  `comsol_output_framework.md`.

  It formalizes:
  1. The Tier 1 / Tier 2 / Tier 3 output taxonomy as a predicate over row records.
  2. Per-feature long-table row validity (feature_flux_long.csv).
  3. Design-level summary row validity (design_outputs.csv).
  4. Bookkeeping invariants that must hold between the per-feature long table
     and the design-level summary (cross-table consistency).
  5. QC gating predicates aligned to the actual pipeline diagnostics.
-/
import Stent.Validity
import Mathlib.Tactic

namespace Stent.Schema

open Stent

/-! ### 1. Per-feature flux row (feature_flux_long.csv) -/

/-- A single row in the per-feature long CSV table.
    Columns: design_id, feature_id, feature_class, zone, area_mm2,
             signed_flux_ml_min, abs_flux_ml_min, axial_x_mm.
    The `normalizedX` field is the axial coordinate normalized to [0,1]. -/
structure FeatureFluxRow where
  designId   : String
  featureId  : FeatureId
  featureClass : FeatureClass
  zone       : Zone
  areaMm2    : ℝ
  signedFlux : ℝ          -- ml/min, sign convention: positive = into lumen
  absFlux    : ℝ          -- ml/min
  axialXMm   : ℝ          -- mm, raw axial coordinate
  normalizedX : Option ℝ  -- axial coordinate normalized to [0,1]

/-- Internal consistency of a single feature-flux row:
    the absolute flux field equals |signedFlux|, area is nonneg,
    and the optional normalizedX (if present) lies in [0,1]. -/
def FeatureFluxRow.isConsistent (row : FeatureFluxRow) : Prop :=
  row.absFlux = |row.signedFlux|
  ∧ 0 ≤ row.areaMm2
  ∧ ∀ nx ∈ row.normalizedX, nx ∈ Set.Icc (0 : ℝ) 1

theorem FeatureFluxRow.absFlux_nonneg_of_consistent
    {row : FeatureFluxRow} (h : row.isConsistent) :
    0 ≤ row.absFlux := by
  rw [h.1]
  exact abs_nonneg _

/-- Convert a FeatureFluxRow back into the internal FeatureFlux representation. -/
def FeatureFluxRow.toFeatureFlux (row : FeatureFluxRow) : FeatureFlux :=
  { feature :=
      { id := row.featureId
        featureClass := row.featureClass
        zone := row.zone
        axialX := row.axialXMm
        normalizedX := row.normalizedX }
    signedFlux := row.signedFlux }

theorem FeatureFluxRow.toFeatureFlux_signedFlux (row : FeatureFluxRow) :
    row.toFeatureFlux.signedFlux = row.signedFlux := rfl

theorem FeatureFluxRow.toFeatureFlux_absFlux_of_consistent
    {row : FeatureFluxRow} (h : row.isConsistent) :
    row.toFeatureFlux.absFlux = row.absFlux := by
  simp [FeatureFlux.absFlux, toFeatureFlux, h.1]

/-! ### 2. Design-level summary row (design_outputs.csv) -/

/-- A single row in the design-level summary CSV.
    Contains the Tier 1 required outputs from the COMSOL output framework. -/
structure DesignSummaryRow where
  designId        : String
  -- Global drainage (Tier 1)
  qOutMlMin       : ℝ
  deltaPPa        : ℝ
  conductance     : ℝ   -- ml_min / Pa
  -- Pathway partitioning (Tier 1)
  qLumenOutMlMin  : ℝ
  qAnnulusOutMlMin : ℝ
  fracLumenOut     : ℝ
  fracAnnulusOut   : ℝ
  -- Side-hole summary (Tier 1)
  qHolesNetMlMin  : ℝ
  qHolesAbsMlMin  : ℝ
  nActiveHoles    : Nat
  -- Zone-disaggregated hole flux (Tier 1)
  proxHoleAbsFlux : ℝ
  midHoleAbsFlux  : ℝ
  distHoleAbsFlux : ℝ
  -- Unroofed-region (Tier 1)
  qUnroofNetMlMin : ℝ
  qUnroofAbsMlMin : ℝ
  fracUnroofOfTotal : ℝ
  -- Pressure references (Tier 1)
  pInAvgPa        : ℝ
  pOutAvgPa       : ℝ
  -- QC diagnostics (Tier 2)
  qInMlMin         : ℝ
  massBalanceRelErr : ℝ
  solverConverged   : Bool
  -- Total exchange (Tier 2, computed)
  qExchangeTotalAbs : ℝ

/-! ### 3. Tier 1 consistency predicates -/

/-- The pressure drop in the summary row equals p_in - p_out. -/
def DesignSummaryRow.deltaPConsistent (row : DesignSummaryRow) : Prop :=
  row.deltaPPa = row.pInAvgPa - row.pOutAvgPa

/-- Conductance = Q_out / deltaP when deltaP > 0. -/
def DesignSummaryRow.conductanceConsistent (row : DesignSummaryRow) : Prop :=
  row.deltaPPa ≠ 0 → row.conductance = row.qOutMlMin / row.deltaPPa

/-- Pathway fractions sum to 1 (up to numerical noise). -/
def DesignSummaryRow.pathwayPartitionConsistent (row : DesignSummaryRow) : Prop :=
  row.qOutMlMin ≠ 0 →
    row.fracLumenOut = row.qLumenOutMlMin / row.qOutMlMin
    ∧ row.fracAnnulusOut = row.qAnnulusOutMlMin / row.qOutMlMin

/-- Unroofed fraction consistent with total. -/
def DesignSummaryRow.unroofFractionConsistent (row : DesignSummaryRow) : Prop :=
  row.qOutMlMin ≠ 0 →
    row.fracUnroofOfTotal = row.qUnroofAbsMlMin / row.qOutMlMin

/-- Zone-disaggregated hole fluxes sum to total hole absolute flux. -/
def DesignSummaryRow.zoneHoleSumConsistent (row : DesignSummaryRow) : Prop :=
  row.proxHoleAbsFlux + row.midHoleAbsFlux + row.distHoleAbsFlux = row.qHolesAbsMlMin

/-- Total exchange = holes + unroofed. -/
def DesignSummaryRow.exchangeTotalConsistent (row : DesignSummaryRow) : Prop :=
  row.qExchangeTotalAbs = row.qHolesAbsMlMin + row.qUnroofAbsMlMin

/-- All Tier 1 consistency conditions hold simultaneously. -/
def DesignSummaryRow.tier1Consistent (row : DesignSummaryRow) : Prop :=
  row.deltaPConsistent
  ∧ row.conductanceConsistent
  ∧ row.pathwayPartitionConsistent
  ∧ row.unroofFractionConsistent
  ∧ row.zoneHoleSumConsistent
  ∧ row.exchangeTotalConsistent

/-! ### 4. Cross-table consistency: per-feature → summary -/

/-- Given a list of consistent feature-flux rows from the same design,
    the summary row's zone-disaggregated totals match the corresponding
    zone-filtered sums of individual row absolute fluxes. -/
def crossTableZoneConsistent
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow) : Prop :=
  let holeRows := rows.filter (fun r => r.featureClass = FeatureClass.holeCap)
  let proxRows := holeRows.filter (fun r => r.zone = Zone.prox)
  let midRows  := holeRows.filter (fun r => r.zone = Zone.mid)
  let distRows := holeRows.filter (fun r => r.zone = Zone.dist)
  summary.proxHoleAbsFlux = (proxRows.map (·.absFlux)).sum
  ∧ summary.midHoleAbsFlux = (midRows.map (·.absFlux)).sum
  ∧ summary.distHoleAbsFlux = (distRows.map (·.absFlux)).sum

/-- Net signed hole flux in the summary equals the sum of signed fluxes
    over all holeCap rows. -/
def crossTableNetFluxConsistent
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow) : Prop :=
  let holeRows := rows.filter (fun r => r.featureClass = FeatureClass.holeCap)
  summary.qHolesNetMlMin = (holeRows.map (·.signedFlux)).sum

/-- Full cross-table consistency. -/
def crossTableConsistent
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow) : Prop :=
  crossTableZoneConsistent rows summary
  ∧ crossTableNetFluxConsistent rows summary

/-! ### 5. QC gating aligned to the pipeline -/

/-- Pipeline QC gate: solver converged and mass balance relative error
    is within tolerance. -/
structure QCConfig where
  massBalanceTol : ℝ
  massBalanceTol_nonneg : 0 ≤ massBalanceTol := by positivity

def DesignSummaryRow.passesQC (cfg : QCConfig) (row : DesignSummaryRow) : Prop :=
  row.solverConverged = true
  ∧ |row.massBalanceRelErr| ≤ cfg.massBalanceTol

/-- If a design summary passes QC, then the solver converged. -/
theorem DesignSummaryRow.passesQC_solver
    {cfg : QCConfig} {row : DesignSummaryRow}
    (h : row.passesQC cfg) :
    row.solverConverged = true := h.1

/-- If a design summary passes QC, mass balance is bounded. -/
theorem DesignSummaryRow.passesQC_massBalance
    {cfg : QCConfig} {row : DesignSummaryRow}
    (h : row.passesQC cfg) :
    |row.massBalanceRelErr| ≤ cfg.massBalanceTol := h.2

/-! ### 6. Lifting from DesignSummaryRow to RawSample -/

/-- Convert a QC-passing design summary row to a RawSample.
    This bridges the schema layer to the existing Validity layer. -/
def DesignSummaryRow.toRawSample
    (row : DesignSummaryRow) (features : List FeatureFlux) : RawSample :=
  { pressureIn? := some row.pInAvgPa
    pressureOut? := some row.pOutAvgPa
    qOut? := some row.qOutMlMin
    features := features
    requiredStatuses :=
      if row.solverConverged then [EvalStatus.ok] else [EvalStatus.exception]
    massBalanceResidual := row.massBalanceRelErr }

/-- A QC-passing summary row's RawSample has all core fields present. -/
theorem DesignSummaryRow.toRawSample_coreFields
    (row : DesignSummaryRow) (features : List FeatureFlux) :
    CoreFieldsPresent (row.toRawSample features) := by
  simp [toRawSample, CoreFieldsPresent]

/-- A QC-passing summary row yields a valid sample when the QC tolerance
    is compatible with the validity config's residual tolerance. -/
theorem DesignSummaryRow.toRawSample_valid
    {qcCfg : QCConfig} {valCfg : ValidityConfig}
    {row : DesignSummaryRow} {features : List FeatureFlux}
    (hqc : row.passesQC qcCfg)
    (htol : qcCfg.massBalanceTol ≤ valCfg.residualTol) :
    ValidSample valCfg (row.toRawSample features) := by
  refine ⟨row.toRawSample_coreFields features, ?_, ?_⟩
  · intro status hmem
    simp [toRawSample, hqc.1] at hmem
    exact hmem
  · exact le_trans hqc.2 htol

/-- Once we know a summary row is valid, derived outputs can be computed. -/
theorem DesignSummaryRow.derivedOutputs_isSome
    {qcCfg : QCConfig} {valCfg : ValidityConfig}
    {row : DesignSummaryRow} {features : List FeatureFlux}
    (hqc : row.passesQC qcCfg)
    (htol : qcCfg.massBalanceTol ≤ valCfg.residualTol) :
    (derivedOutputs? (row.toRawSample features)).isSome := by
  exact derivedOutputs?_isSome_of_valid (row.toRawSample_valid hqc htol)

/-- The pressure drop in the derived outputs matches the summary's pressure drop,
    provided the summary is deltaP-consistent. -/
theorem DesignSummaryRow.derivedOutputs_pressureDrop
    (row : DesignSummaryRow) (features : List FeatureFlux)
    (_hcons : row.deltaPConsistent) :
    derivedOutputs? (row.toRawSample features) =
      some { pressureDrop := row.pInAvgPa - row.pOutAvgPa
             qOut := row.qOutMlMin
             exchangeTotal := totalExchangeMetric features
             centroid := Option.none
             spread := Option.none } := by
  simp [derivedOutputs?, toRawSample, pressureDrop]

theorem DesignSummaryRow.derivedOutputs_deltaP_eq
    (row : DesignSummaryRow) (features : List FeatureFlux)
    (hcons : row.deltaPConsistent) :
    ∃ agg, derivedOutputs? (row.toRawSample features) = some agg
      ∧ agg.pressureDrop = row.deltaPPa := by
  refine ⟨_, row.derivedOutputs_pressureDrop features hcons, ?_⟩
  exact hcons.symm

/-! ### 7. Zone sum recovery from feature rows -/

/-- If all feature-flux rows are internally consistent, then the sum of
    absFlux fields over holeCap rows equals the totalAbsExchange of their
    converted FeatureFlux list. -/
theorem featureRows_totalAbsExchange
    (rows : List FeatureFluxRow)
    (hcons : ∀ r ∈ rows, r.isConsistent) :
    totalAbsExchange (rows.map (·.toFeatureFlux)) =
      (rows.map (·.absFlux)).sum := by
  induction rows with
  | nil => simp [totalAbsExchange]
  | cons r rs ih =>
    simp only [List.map_cons, totalAbsExchange, List.sum_cons]
    have hr : r.isConsistent := hcons r (List.mem_cons.mpr (Or.inl rfl))
    rw [r.toFeatureFlux_absFlux_of_consistent hr]
    congr 1
    exact ih (fun r' hr' => hcons r' (List.mem_cons.mpr (Or.inr hr')))

/-! ### 8. Nonnegativity of summary zone totals -/

/-- If all feature-flux rows are consistent, zone-disaggregated totals
    in a cross-table-consistent summary are nonneg. -/
theorem crossTable_proxHoleAbsFlux_nonneg
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow)
    (hcons : ∀ r ∈ rows, r.isConsistent)
    (hcross : crossTableZoneConsistent rows summary) :
    0 ≤ summary.proxHoleAbsFlux := by
  rw [hcross.1]
  apply List.sum_nonneg
  intro x hx
  simp only [List.mem_map] at hx
  obtain ⟨r, hr, rfl⟩ := hx
  simp only [List.mem_filter, decide_eq_true_eq] at hr
  exact FeatureFluxRow.absFlux_nonneg_of_consistent (hcons r hr.1.1)

theorem crossTable_midHoleAbsFlux_nonneg
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow)
    (hcons : ∀ r ∈ rows, r.isConsistent)
    (hcross : crossTableZoneConsistent rows summary) :
    0 ≤ summary.midHoleAbsFlux := by
  rw [hcross.2.1]
  apply List.sum_nonneg
  intro x hx
  simp only [List.mem_map] at hx
  obtain ⟨r, hr, rfl⟩ := hx
  simp only [List.mem_filter, decide_eq_true_eq] at hr
  exact FeatureFluxRow.absFlux_nonneg_of_consistent (hcons r hr.1.1)

theorem crossTable_distHoleAbsFlux_nonneg
    (rows : List FeatureFluxRow) (summary : DesignSummaryRow)
    (hcons : ∀ r ∈ rows, r.isConsistent)
    (hcross : crossTableZoneConsistent rows summary) :
    0 ≤ summary.distHoleAbsFlux := by
  rw [hcross.2.2]
  apply List.sum_nonneg
  intro x hx
  simp only [List.mem_map] at hx
  obtain ⟨r, hr, rfl⟩ := hx
  simp only [List.mem_filter, decide_eq_true_eq] at hr
  exact FeatureFluxRow.absFlux_nonneg_of_consistent (hcons r hr.1.1)

end Stent.Schema
