import Stent.Metrics
import Mathlib.Analysis.SpecialFunctions.Log.Basic

namespace Stent

structure AggregateOutputs where
  pressureDrop : ℝ
  qOut : ℝ
  exchangeTotal : ℝ
  centroid : Option ℝ := none
  spread : Option ℝ := none

structure ObjectiveTerm (α : Type) where
  name : String
  weight : ℝ
  eval : α → ℝ

def weightedObjective {α : Type} (terms : List (ObjectiveTerm α)) (x : α) : ℝ :=
  (terms.map (fun term => term.weight * term.eval x)).sum

def optionValue (fallback : ℝ) : Option ℝ → ℝ
  | some x => x
  | none => fallback

structure CanonicalWeights where
  pressureDropPenalty : ℝ := 1
  outletFlowReward : ℝ := 1
  exchangeReward : ℝ := 1
  centroidTarget : ℝ := 1 / 2
  centroidPenalty : ℝ := 0
  spreadPenalty : ℝ := 0

def canonicalPhysicalObjective (weights : CanonicalWeights) (outputs : AggregateOutputs) : ℝ :=
  weights.pressureDropPenalty * outputs.pressureDrop
    - weights.outletFlowReward * outputs.qOut
    - weights.exchangeReward * outputs.exchangeTotal
    + weights.centroidPenalty * (optionValue 0 outputs.centroid - weights.centroidTarget) ^ 2
    + weights.spreadPenalty * optionValue 0 outputs.spread

namespace Transform

def identity (x : ℝ) : ℝ := x

noncomputable def logPositive (x : {x : ℝ // 0 < x}) : ℝ := Real.log x.1

noncomputable def unitNormalize (lo hi : ℝ) (x : Set.Icc lo hi) : ℝ :=
  (x.1 - lo) / (hi - lo)

def clamp01 (x : ℝ) : ℝ := max 0 (min 1 x)

theorem identity_apply (x : ℝ) : identity x = x := rfl

theorem logPositive_spec (x : {x : ℝ // 0 < x}) : logPositive x = Real.log x.1 := rfl

theorem clamp01_mem_Icc (x : ℝ) : clamp01 x ∈ Set.Icc (0 : ℝ) 1 := by
  constructor
  · simp [clamp01]
  · have hupper : max 0 (min 1 x) ≤ 1 := by
      exact max_le (by norm_num) (min_le_left _ _)
    simpa [clamp01] using hupper

theorem unitNormalize_mem_Icc
    (lo hi : ℝ)
    (x : Set.Icc lo hi)
    (hlohi : lo < hi) :
    unitNormalize lo hi x ∈ Set.Icc (0 : ℝ) 1 := by
  constructor
  · have hnum : 0 ≤ x.1 - lo := by
      exact sub_nonneg.mpr x.2.1
    exact div_nonneg hnum (le_of_lt (sub_pos.mpr hlohi))
  · have hden : 0 ≤ hi - lo := le_of_lt (sub_pos.mpr hlohi)
    have hne : hi - lo ≠ 0 := by
      linarith
    have hnum : x.1 - lo ≤ hi - lo := by
      linarith [x.2.2]
    have hdiv : (x.1 - lo) / (hi - lo) ≤ (hi - lo) / (hi - lo) := by
      exact div_le_div_of_nonneg_right hnum hden
    have hone : (hi - lo) / (hi - lo) = (1 : ℝ) := by
      field_simp [hne]
    rw [hone] at hdiv
    simpa [unitNormalize] using hdiv

end Transform

end Stent
