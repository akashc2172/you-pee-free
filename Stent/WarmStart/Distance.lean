import Stent.Feature
import Mathlib.Tactic

namespace Stent.WarmStart

open Stent

structure TopologyLabel where
  name : String
  deriving DecidableEq, Repr

structure DesignVector where
  stentLength : ℝ
  holeCount : Nat
  holeDiameter : ℝ
  unroofFraction : ℝ
  proxCount : Nat
  midCount : Nat
  distCount : Nat
  topology : TopologyLabel
  sourceFamily : Option SourceType := none

structure DistanceScales where
  stentLength : ℝ
  holeCount : ℝ
  holeDiameter : ℝ
  unroofFraction : ℝ
  proxCount : ℝ
  midCount : ℝ
  distCount : ℝ
  stentLength_pos : 0 < stentLength
  holeCount_pos : 0 < holeCount
  holeDiameter_pos : 0 < holeDiameter
  unroofFraction_pos : 0 < unroofFraction
  proxCount_pos : 0 < proxCount
  midCount_pos : 0 < midCount
  distCount_pos : 0 < distCount

structure DistanceWeights where
  stentLength : ℝ := 1
  holeCount : ℝ := 1
  holeDiameter : ℝ := 1
  unroofFraction : ℝ := 1
  proxCount : ℝ := 1
  midCount : ℝ := 1
  distCount : ℝ := 1
  topologyMismatch : ℝ := 1
  sourceMismatch : ℝ := 0
  stentLength_nonneg : 0 ≤ stentLength := by positivity
  holeCount_nonneg : 0 ≤ holeCount := by positivity
  holeDiameter_nonneg : 0 ≤ holeDiameter := by positivity
  unroofFraction_nonneg : 0 ≤ unroofFraction := by positivity
  proxCount_nonneg : 0 ≤ proxCount := by positivity
  midCount_nonneg : 0 ≤ midCount := by positivity
  distCount_nonneg : 0 ≤ distCount := by positivity
  topologyMismatch_nonneg : 0 ≤ topologyMismatch := by positivity
  sourceMismatch_nonneg : 0 ≤ sourceMismatch := by positivity

structure DistanceConfig where
  scales : DistanceScales
  weights : DistanceWeights

noncomputable def sqNormDiff (scale x y : ℝ) : ℝ :=
  ((x - y) / scale) ^ 2

noncomputable def natSqNormDiff (scale : ℝ) (x y : Nat) : ℝ :=
  sqNormDiff scale x y

def mismatchPenalty (penalty : ℝ) {α : Type} [DecidableEq α] (x y : α) : ℝ :=
  if x = y then 0 else penalty

noncomputable def score (cfg : DistanceConfig) (x y : DesignVector) : ℝ :=
  cfg.weights.stentLength * sqNormDiff cfg.scales.stentLength x.stentLength y.stentLength
    + cfg.weights.holeCount * natSqNormDiff cfg.scales.holeCount x.holeCount y.holeCount
    + cfg.weights.holeDiameter * sqNormDiff cfg.scales.holeDiameter x.holeDiameter y.holeDiameter
    + cfg.weights.unroofFraction * sqNormDiff cfg.scales.unroofFraction x.unroofFraction y.unroofFraction
    + cfg.weights.proxCount * natSqNormDiff cfg.scales.proxCount x.proxCount y.proxCount
    + cfg.weights.midCount * natSqNormDiff cfg.scales.midCount x.midCount y.midCount
    + cfg.weights.distCount * natSqNormDiff cfg.scales.distCount x.distCount y.distCount
    + mismatchPenalty cfg.weights.topologyMismatch x.topology y.topology
    + mismatchPenalty cfg.weights.sourceMismatch x.sourceFamily y.sourceFamily

theorem sqNormDiff_nonneg (scale x y : ℝ) : 0 ≤ sqNormDiff scale x y := by
  unfold sqNormDiff
  positivity

theorem sqNormDiff_symm (scale x y : ℝ) : sqNormDiff scale x y = sqNormDiff scale y x := by
  unfold sqNormDiff
  ring_nf

theorem mismatchPenalty_nonneg
    (penalty : ℝ)
    (hpenalty : 0 ≤ penalty)
    {α : Type} [DecidableEq α] (x y : α) :
    0 ≤ mismatchPenalty penalty x y := by
  by_cases hxy : x = y <;> simp [mismatchPenalty, hxy, hpenalty]

theorem mismatchPenalty_symm
    (penalty : ℝ)
    {α : Type} [DecidableEq α] (x y : α) :
    mismatchPenalty penalty x y = mismatchPenalty penalty y x := by
  by_cases hxy : x = y
  · subst hxy
    simp [mismatchPenalty]
  · have hyx : y ≠ x := by
        intro hyx
        exact hxy hyx.symm
    simp [mismatchPenalty, hxy, hyx]

theorem score_nonneg (cfg : DistanceConfig) (x y : DesignVector) : 0 ≤ score cfg x y := by
  unfold score
  have h₁ := cfg.weights.stentLength_nonneg
  have h₂ := cfg.weights.holeCount_nonneg
  have h₃ := cfg.weights.holeDiameter_nonneg
  have h₄ := cfg.weights.unroofFraction_nonneg
  have h₅ := cfg.weights.proxCount_nonneg
  have h₆ := cfg.weights.midCount_nonneg
  have h₇ := cfg.weights.distCount_nonneg
  have h₈ := cfg.weights.topologyMismatch_nonneg
  have h₉ := cfg.weights.sourceMismatch_nonneg
  have hs₁ : 0 ≤ cfg.weights.stentLength * sqNormDiff cfg.scales.stentLength x.stentLength y.stentLength := by
    exact mul_nonneg h₁ (sqNormDiff_nonneg _ _ _)
  have hs₂ : 0 ≤ cfg.weights.holeCount * natSqNormDiff cfg.scales.holeCount x.holeCount y.holeCount := by
    exact mul_nonneg h₂ (sqNormDiff_nonneg _ _ _)
  have hs₃ : 0 ≤ cfg.weights.holeDiameter * sqNormDiff cfg.scales.holeDiameter x.holeDiameter y.holeDiameter := by
    exact mul_nonneg h₃ (sqNormDiff_nonneg _ _ _)
  have hs₄ : 0 ≤ cfg.weights.unroofFraction * sqNormDiff cfg.scales.unroofFraction x.unroofFraction y.unroofFraction := by
    exact mul_nonneg h₄ (sqNormDiff_nonneg _ _ _)
  have hs₅ : 0 ≤ cfg.weights.proxCount * natSqNormDiff cfg.scales.proxCount x.proxCount y.proxCount := by
    exact mul_nonneg h₅ (sqNormDiff_nonneg _ _ _)
  have hs₆ : 0 ≤ cfg.weights.midCount * natSqNormDiff cfg.scales.midCount x.midCount y.midCount := by
    exact mul_nonneg h₆ (sqNormDiff_nonneg _ _ _)
  have hs₇ : 0 ≤ cfg.weights.distCount * natSqNormDiff cfg.scales.distCount x.distCount y.distCount := by
    exact mul_nonneg h₇ (sqNormDiff_nonneg _ _ _)
  have hs₈ : 0 ≤ mismatchPenalty cfg.weights.topologyMismatch x.topology y.topology := by
    exact mismatchPenalty_nonneg _ h₈ _ _
  have hs₉ : 0 ≤ mismatchPenalty cfg.weights.sourceMismatch x.sourceFamily y.sourceFamily := by
    exact mismatchPenalty_nonneg _ h₉ _ _
  linarith

theorem score_symm (cfg : DistanceConfig) (x y : DesignVector) :
    score cfg x y = score cfg y x := by
  unfold score
  simp [sqNormDiff_symm, natSqNormDiff, mismatchPenalty_symm, add_assoc, add_left_comm, add_comm]

theorem score_self (cfg : DistanceConfig) (x : DesignVector) : score cfg x x = 0 := by
  unfold score
  simp [sqNormDiff, natSqNormDiff, mismatchPenalty]

theorem score_self_le (cfg : DistanceConfig) (x y : DesignVector) :
    score cfg x x ≤ score cfg x y := by
  simp [score_self, score_nonneg]

end Stent.WarmStart
