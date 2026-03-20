import Stent.Feature
import Stent.FluxBookkeeping
import Stent.Metrics
import Stent.WarmStart.Policy
import Mathlib.Tactic

namespace Stent

open WarmStart

noncomputable def toyFeatureA : Feature :=
  { id := ⟨1⟩
    featureClass := FeatureClass.holeCap
    zone := Zone.prox
    sourceType := some SourceType.shaft
    axialX := 10
    normalizedX := some (1 / 4) }

noncomputable def toyFeatureB : Feature :=
  { id := ⟨2⟩
    featureClass := FeatureClass.holeCap
    zone := Zone.mid
    sourceType := some SourceType.shaft
    axialX := 20
    normalizedX := some (1 / 2) }

noncomputable def toyFeatureC : Feature :=
  { id := ⟨3⟩
    featureClass := FeatureClass.unroofPatch
    zone := Zone.dist
    sourceType := some SourceType.shaft
    axialX := 30
    openLength := some 5
    normalizedX := some (3 / 4) }

noncomputable def toyFluxes : List FeatureFlux :=
  [ { feature := toyFeatureA, signedFlux := 1 }
  , { feature := toyFeatureB, signedFlux := -2 }
  , { feature := toyFeatureC, signedFlux := 3 } ]

example : totalSignedExchange toyFluxes = 2 := by
  norm_num [toyFluxes, totalSignedExchange]

example : totalAbsExchange toyFluxes = 6 := by
  norm_num [toyFluxes, totalAbsExchange, FeatureFlux.absFlux]

example : zoneAbsExchange Zone.prox toyFluxes = 1 := by
  simp [zoneAbsExchange, zoneEntries, subsetEntries, toyFluxes, totalAbsExchange, FeatureFlux.absFlux,
    toyFeatureA, toyFeatureB, toyFeatureC]

noncomputable def toyWeightedPoints : List WeightedCoordinate :=
  [ { coord := 1 / 4, weight := 1 }
  , { coord := 1 / 2, weight := 2 }
  , { coord := 3 / 4, weight := 1 } ]

example : rawCentroid toyWeightedPoints = 1 / 2 := by
  norm_num [rawCentroid, toyWeightedPoints, weightedCoordSum, totalWeight]

example : exchangeSpread toyWeightedPoints = 1 / 32 := by
  norm_num [exchangeSpread, spreadNumerator, weightedSquareDeviation, rawCentroid,
    toyWeightedPoints, weightedCoordSum, totalWeight]

def topoA : TopologyLabel := ⟨"baseline-shaft"⟩

noncomputable def toyDesignTarget : DesignVector :=
  { stentLength := 140
    holeCount := 12
    holeDiameter := 0.4
    unroofFraction := 0.1
    proxCount := 4
    midCount := 4
    distCount := 4
    topology := topoA
    sourceFamily := some SourceType.shaft }

noncomputable def toyDesignNear : DesignVector :=
  { stentLength := 140
    holeCount := 12
    holeDiameter := 0.4
    unroofFraction := 0.1
    proxCount := 4
    midCount := 4
    distCount := 4
    topology := topoA
    sourceFamily := some SourceType.shaft }

noncomputable def toyDesignFar : DesignVector :=
  { stentLength := 180
    holeCount := 24
    holeDiameter := 0.8
    unroofFraction := 0.4
    proxCount := 8
    midCount := 8
    distCount := 8
    topology := ⟨"coil-mix"⟩
    sourceFamily := some SourceType.coil }

noncomputable def toyScales : DistanceScales :=
  { stentLength := 20
    holeCount := 10
    holeDiameter := 0.2
    unroofFraction := 0.2
    proxCount := 4
    midCount := 4
    distCount := 4
    stentLength_pos := by positivity
    holeCount_pos := by positivity
    holeDiameter_pos := by positivity
    unroofFraction_pos := by positivity
    proxCount_pos := by positivity
    midCount_pos := by positivity
    distCount_pos := by positivity }

noncomputable def toyWeights : DistanceWeights :=
  { topologyMismatch := 4
    sourceMismatch := 2 }

noncomputable def toyCfg : DistanceConfig :=
  { scales := toyScales
    weights := toyWeights }

noncomputable def toyAnchors : List Anchor :=
  [ { anchorId := 11, design := toyDesignFar }
  , { anchorId := 5, design := toyDesignNear } ]

example : anchorScore toyCfg toyDesignTarget ⟨5, toyDesignNear⟩ = 0 := by
  change score toyCfg toyDesignTarget toyDesignNear = 0
  simp [toyDesignNear, toyDesignTarget, score_self]

example : selectNearest? toyCfg toyDesignTarget toyAnchors = some ⟨5, toyDesignNear⟩ := by
  have hnear : anchorScore toyCfg toyDesignTarget ⟨5, toyDesignNear⟩ = 0 := by
    simpa [anchorScore] using (show score toyCfg toyDesignTarget toyDesignNear = 0 by
      simp [toyDesignNear, toyDesignTarget, score_self])
  have htopo : ("baseline-shaft" : String) ≠ "coil-mix" := by decide
  have hsource : SourceType.shaft ≠ SourceType.coil := by decide
  have hfarEq : anchorScore toyCfg toyDesignTarget ⟨11, toyDesignFar⟩ = 2069 / 100 := by
    norm_num [anchorScore, toyCfg, toyWeights, toyScales, topoA, toyDesignTarget, toyDesignFar,
      score, sqNormDiff, natSqNormDiff, mismatchPenalty, htopo, hsource]
  have hfar_nonneg : (0 : ℝ) ≤ 2069 / 100 := by norm_num
  simp [selectNearest?, selectNearestCore, chooseBetter, toyAnchors, hnear, hfarEq, hfar_nonneg]

end Stent
