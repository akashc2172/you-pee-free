import Stent.FluxBookkeeping
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Tactic

namespace Stent

def pressureDrop (pIn pOut : ℝ) : ℝ := pIn - pOut

theorem pressureDrop_nonneg_of_le (h : pOut ≤ pIn) : 0 ≤ pressureDrop pIn pOut := by
  dsimp [pressureDrop]
  linarith

theorem pressureDrop_eq_zero_iff (p : ℝ) : pressureDrop p p = 0 := by
  simp [pressureDrop]

theorem pressureDrop_add_out (pIn pOut : ℝ) :
    pressureDrop pIn pOut + pOut = pIn := by
  linarith [show pressureDrop pIn pOut = pIn - pOut by rfl]

def totalExchangeMetric (entries : List FeatureFlux) : ℝ :=
  totalAbsExchange entries

structure WeightedCoordinate where
  coord : ℝ
  weight : ℝ

def totalWeight : List WeightedCoordinate → ℝ
  | [] => 0
  | point :: points => point.weight + totalWeight points

def weightedCoordSum : List WeightedCoordinate → ℝ
  | [] => 0
  | point :: points => point.weight * point.coord + weightedCoordSum points

noncomputable def rawCentroid (points : List WeightedCoordinate) : ℝ :=
  weightedCoordSum points / totalWeight points

noncomputable def centroid? (points : List WeightedCoordinate) : Option ℝ :=
  if h : 0 < totalWeight points then
    some (rawCentroid points)
  else
    none

def weightedSquareDeviation (center : ℝ) : List WeightedCoordinate → ℝ
  | [] => 0
  | point :: points => point.weight * (point.coord - center) ^ 2 + weightedSquareDeviation center points

noncomputable def spreadNumerator (points : List WeightedCoordinate) : ℝ :=
  weightedSquareDeviation (rawCentroid points) points

noncomputable def exchangeSpread (points : List WeightedCoordinate) : ℝ :=
  spreadNumerator points / totalWeight points

noncomputable def boundedLocalizationScore (scale : ℝ) (points : List WeightedCoordinate) : ℝ :=
  max 0 (min 1 (1 - exchangeSpread points / scale))

theorem totalWeight_nonneg
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight) :
    0 ≤ totalWeight points := by
  induction points with
  | nil => simp [totalWeight]
  | cons point points ih =>
      have hhead : 0 ≤ point.weight := hweight point (by simp)
      have htail : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      simp [totalWeight, hhead, ih htail, add_nonneg]

theorem weightedCoordSum_nonneg
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hcoord : ∀ point ∈ points, point.coord ∈ Set.Icc (0 : ℝ) 1) :
    0 ≤ weightedCoordSum points := by
  induction points with
  | nil => simp [weightedCoordSum]
  | cons point points ih =>
      have hheadw : 0 ≤ point.weight := hweight point (by simp)
      have hheadc : point.coord ∈ Set.Icc (0 : ℝ) 1 := hcoord point (by simp)
      have hterm : 0 ≤ point.weight * point.coord := by
        nlinarith [hheadw, hheadc.1]
      have htailw : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      have htailc : ∀ point' ∈ points, point'.coord ∈ Set.Icc (0 : ℝ) 1 := by
        intro point' hmem
        exact hcoord point' (by simp [hmem])
      simp [weightedCoordSum, hterm, ih htailw htailc, add_nonneg]

theorem weightedCoordSum_le_totalWeight
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hcoord : ∀ point ∈ points, point.coord ∈ Set.Icc (0 : ℝ) 1) :
    weightedCoordSum points ≤ totalWeight points := by
  induction points with
  | nil => simp [weightedCoordSum, totalWeight]
  | cons point points ih =>
      have hheadw : 0 ≤ point.weight := hweight point (by simp)
      have hheadc : point.coord ∈ Set.Icc (0 : ℝ) 1 := hcoord point (by simp)
      have hterm : point.weight * point.coord ≤ point.weight := by
        nlinarith [hheadw, hheadc.2]
      have htailw : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      have htailc : ∀ point' ∈ points, point'.coord ∈ Set.Icc (0 : ℝ) 1 := by
        intro point' hmem
        exact hcoord point' (by simp [hmem])
      have htail := ih htailw htailc
      simpa [weightedCoordSum, totalWeight] using add_le_add hterm htail

theorem totalWeight_perm {points₁ points₂ : List WeightedCoordinate}
    (hperm : List.Perm points₁ points₂) :
    totalWeight points₁ = totalWeight points₂ := by
  induction hperm with
  | nil => rfl
  | cons _ _ ih =>
      simp [totalWeight, ih]
  | swap x y xs =>
      simp [totalWeight, add_assoc, add_left_comm, add_comm]
  | trans _ _ ih₁ ih₂ =>
      exact ih₁.trans ih₂

theorem weightedCoordSum_perm {points₁ points₂ : List WeightedCoordinate}
    (hperm : List.Perm points₁ points₂) :
    weightedCoordSum points₁ = weightedCoordSum points₂ := by
  induction hperm with
  | nil => rfl
  | cons _ _ ih =>
      simp [weightedCoordSum, ih]
  | swap x y xs =>
      simp [weightedCoordSum, add_assoc, add_left_comm, add_comm]
  | trans _ _ ih₁ ih₂ =>
      exact ih₁.trans ih₂

theorem weightedSquareDeviation_perm
    (center : ℝ)
    {points₁ points₂ : List WeightedCoordinate}
    (hperm : List.Perm points₁ points₂) :
    weightedSquareDeviation center points₁ = weightedSquareDeviation center points₂ := by
  induction hperm with
  | nil => rfl
  | cons _ _ ih =>
      simp [weightedSquareDeviation, ih]
  | swap x y xs =>
      simp [weightedSquareDeviation, add_assoc, add_left_comm, add_comm]
  | trans _ _ ih₁ ih₂ =>
      exact ih₁.trans ih₂

theorem rawCentroid_perm {points₁ points₂ : List WeightedCoordinate}
    (hperm : List.Perm points₁ points₂) :
    rawCentroid points₁ = rawCentroid points₂ := by
  simp [rawCentroid, weightedCoordSum_perm hperm, totalWeight_perm hperm]

theorem rawCentroid_mem_Icc
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hcoord : ∀ point ∈ points, point.coord ∈ Set.Icc (0 : ℝ) 1)
    (hpos : 0 < totalWeight points) :
    rawCentroid points ∈ Set.Icc (0 : ℝ) 1 := by
  have hsum_nonneg := weightedCoordSum_nonneg points hweight hcoord
  have hsum_le := weightedCoordSum_le_totalWeight points hweight hcoord
  constructor
  · exact div_nonneg hsum_nonneg (le_of_lt hpos)
  · have hne : totalWeight points ≠ 0 := by linarith
    have hmul : weightedCoordSum points ≤ 1 * totalWeight points := by simpa using hsum_le
    have hdiv : weightedCoordSum points / totalWeight points ≤ 1 := by
      field_simp [hne]
      nlinarith
    simpa [rawCentroid] using hdiv

theorem weightedCoordSum_eq_mul_totalWeight_of_commonCoord
    (points : List WeightedCoordinate)
    (c : ℝ)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hconst : ∀ point ∈ points, 0 < point.weight → point.coord = c) :
    weightedCoordSum points = c * totalWeight points := by
  induction points with
  | nil =>
      simp [weightedCoordSum, totalWeight]
  | cons point points ih =>
      have htailw : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      have htailconst : ∀ point' ∈ points, 0 < point'.weight → point'.coord = c := by
        intro point' hmem hgt
        exact hconst point' (by simp [hmem]) hgt
      by_cases hzero : point.weight = 0
      · rw [weightedCoordSum, totalWeight, hzero, zero_mul, zero_add]
        simpa [hzero] using ih htailw htailconst
      · have hgt : 0 < point.weight := by
          have hne : (0 : ℝ) ≠ point.weight := by
            intro h
            exact hzero h.symm
          exact lt_of_le_of_ne (hweight point (by simp)) hne
        have hcoord_eq : point.coord = c := hconst point (by simp) hgt
        rw [weightedCoordSum, totalWeight, hcoord_eq, ih htailw htailconst]
        ring

theorem rawCentroid_eq_commonCoord
    (points : List WeightedCoordinate)
    (c : ℝ)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hconst : ∀ point ∈ points, 0 < point.weight → point.coord = c)
    (hpos : 0 < totalWeight points) :
    rawCentroid points = c := by
  have hsum :=
    weightedCoordSum_eq_mul_totalWeight_of_commonCoord points c hweight hconst
  have hne : totalWeight points ≠ 0 := by linarith
  calc
    rawCentroid points = (c * totalWeight points) / totalWeight points := by
      simp [rawCentroid, hsum]
    _ = c := by
      field_simp [hne]

theorem weightedSquareDeviation_nonneg
    (center : ℝ)
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight) :
    0 ≤ weightedSquareDeviation center points := by
  induction points with
  | nil => simp [weightedSquareDeviation]
  | cons point points ih =>
      have hheadw : 0 ≤ point.weight := hweight point (by simp)
      have hterm : 0 ≤ point.weight * (point.coord - center) ^ 2 := by
        nlinarith [sq_nonneg (point.coord - center), hheadw]
      have htailw : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      simp [weightedSquareDeviation, hterm, ih htailw, add_nonneg]

theorem weightedSquareDeviation_eq_zero_of_commonCoord
    (center : ℝ)
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hconst : ∀ point ∈ points, 0 < point.weight → point.coord = center) :
    weightedSquareDeviation center points = 0 := by
  induction points with
  | nil =>
      simp [weightedSquareDeviation]
  | cons point points ih =>
      have htailw : ∀ point' ∈ points, 0 ≤ point'.weight := by
        intro point' hmem
        exact hweight point' (by simp [hmem])
      have htailconst : ∀ point' ∈ points, 0 < point'.weight → point'.coord = center := by
        intro point' hmem hgt
        exact hconst point' (by simp [hmem]) hgt
      by_cases hzero : point.weight = 0
      · rw [weightedSquareDeviation, hzero, zero_mul, zero_add]
        exact ih htailw htailconst
      · have hgt : 0 < point.weight := by
          have hne : (0 : ℝ) ≠ point.weight := by
            intro h
            exact hzero h.symm
          exact lt_of_le_of_ne (hweight point (by simp)) hne
        have hcoord_eq : point.coord = center := hconst point (by simp) hgt
        rw [weightedSquareDeviation, hcoord_eq, sub_self, zero_pow (by decide), mul_zero, zero_add]
        exact ih htailw htailconst

theorem exchangeSpread_nonneg
    (points : List WeightedCoordinate)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hpos : 0 < totalWeight points) :
    0 ≤ exchangeSpread points := by
  have hnum := weightedSquareDeviation_nonneg (rawCentroid points) points hweight
  exact div_nonneg hnum (le_of_lt hpos)

theorem exchangeSpread_perm {points₁ points₂ : List WeightedCoordinate}
    (hperm : List.Perm points₁ points₂) :
    exchangeSpread points₁ = exchangeSpread points₂ := by
  unfold exchangeSpread spreadNumerator
  rw [rawCentroid_perm hperm]
  rw [weightedSquareDeviation_perm (rawCentroid points₂) hperm]
  rw [totalWeight_perm hperm]

theorem exchangeSpread_eq_zero_of_commonCoord
    (points : List WeightedCoordinate)
    (c : ℝ)
    (hweight : ∀ point ∈ points, 0 ≤ point.weight)
    (hconst : ∀ point ∈ points, 0 < point.weight → point.coord = c)
    (hpos : 0 < totalWeight points) :
    exchangeSpread points = 0 := by
  have hcentroid : rawCentroid points = c :=
    rawCentroid_eq_commonCoord points c hweight hconst hpos
  have hnum :
      weightedSquareDeviation (rawCentroid points) points = 0 := by
    simpa [hcentroid] using
      weightedSquareDeviation_eq_zero_of_commonCoord c points hweight hconst
  have hne : totalWeight points ≠ 0 := by linarith
  simp [exchangeSpread, spreadNumerator, hnum]

theorem boundedLocalizationScore_mem_Icc
    (scale : ℝ)
    (points : List WeightedCoordinate)
    (_hscale : 0 < scale) :
    boundedLocalizationScore scale points ∈ Set.Icc (0 : ℝ) 1 := by
  constructor
  · simp [boundedLocalizationScore]
  · have hupper : max 0 (min 1 (1 - exchangeSpread points / scale)) ≤ 1 := by
      exact max_le (by norm_num) (min_le_left _ _)
    simp [boundedLocalizationScore, hupper]

end Stent
