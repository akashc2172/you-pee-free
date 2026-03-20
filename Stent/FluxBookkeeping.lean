import Stent.Feature
import Mathlib.Algebra.BigOperators.Ring.List

namespace Stent

structure FeatureFlux where
  feature : Feature
  signedFlux : ℝ

def FeatureFlux.absFlux (entry : FeatureFlux) : ℝ := |entry.signedFlux|

theorem FeatureFlux.absFlux_nonneg (entry : FeatureFlux) : 0 ≤ entry.absFlux := by
  exact abs_nonneg entry.signedFlux

def totalSignedExchange : List FeatureFlux → ℝ
  | [] => 0
  | entry :: entries => entry.signedFlux + totalSignedExchange entries

def totalAbsExchange : List FeatureFlux → ℝ
  | [] => 0
  | entry :: entries => entry.absFlux + totalAbsExchange entries

def subsetEntries (P : Feature → Prop) [DecidablePred P] (entries : List FeatureFlux) :
    List FeatureFlux :=
  entries.filter (fun entry => P entry.feature)

def subsetAbsExchange (P : Feature → Prop) [DecidablePred P] (entries : List FeatureFlux) : ℝ :=
  totalAbsExchange (subsetEntries P entries)

def zoneEntries (zone : Zone) (entries : List FeatureFlux) : List FeatureFlux :=
  subsetEntries (fun feature => feature.zone = zone) entries

def classEntries (featureClass : FeatureClass) (entries : List FeatureFlux) : List FeatureFlux :=
  subsetEntries (fun feature => feature.featureClass = featureClass) entries

def zoneSignedExchange (zone : Zone) (entries : List FeatureFlux) : ℝ :=
  totalSignedExchange (zoneEntries zone entries)

def zoneAbsExchange (zone : Zone) (entries : List FeatureFlux) : ℝ :=
  totalAbsExchange (zoneEntries zone entries)

def classAbsExchange (featureClass : FeatureClass) (entries : List FeatureFlux) : ℝ :=
  totalAbsExchange (classEntries featureClass entries)

theorem totalAbsExchange_nonneg (entries : List FeatureFlux) : 0 ≤ totalAbsExchange entries := by
  induction entries with
  | nil => simp [totalAbsExchange]
  | cons entry entries ih =>
      simp [totalAbsExchange, entry.absFlux_nonneg, ih, add_nonneg]

theorem totalAbsExchange_eq_zero_of_all_abs_zero
    (entries : List FeatureFlux)
    (hzero : ∀ entry ∈ entries, entry.absFlux = 0) :
    totalAbsExchange entries = 0 := by
  induction entries with
  | nil => simp [totalAbsExchange]
  | cons entry entries ih =>
      have hhead : entry.absFlux = 0 := hzero entry (by simp)
      have htail : ∀ entry' ∈ entries, entry'.absFlux = 0 := by
        intro entry' hmem
        exact hzero entry' (by simp [hmem])
      simp [totalAbsExchange, hhead, ih htail]

theorem zoneAbsExchange_nonneg (zone : Zone) (entries : List FeatureFlux) :
    0 ≤ zoneAbsExchange zone entries := by
  exact totalAbsExchange_nonneg _

theorem classAbsExchange_nonneg (featureClass : FeatureClass) (entries : List FeatureFlux) :
    0 ≤ classAbsExchange featureClass entries := by
  exact totalAbsExchange_nonneg _

theorem zoneAbsExchange_sum (entries : List FeatureFlux) :
    zoneAbsExchange Zone.prox entries
      + zoneAbsExchange Zone.mid entries
      + zoneAbsExchange Zone.dist entries
      = totalAbsExchange entries := by
  induction entries with
  | nil =>
      simp [zoneAbsExchange, zoneEntries, subsetEntries, totalAbsExchange]
  | cons entry entries ih =>
      cases hzone : entry.feature.zone
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [zoneAbsExchange, zoneEntries, subsetEntries, totalAbsExchange,
          hzone, add_assoc, add_left_comm, add_comm] using hstep
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [zoneAbsExchange, zoneEntries, subsetEntries, totalAbsExchange,
          hzone, add_assoc, add_left_comm, add_comm] using hstep
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [zoneAbsExchange, zoneEntries, subsetEntries, totalAbsExchange,
          hzone, add_assoc, add_left_comm, add_comm] using hstep

theorem classAbsExchange_sum (entries : List FeatureFlux) :
    classAbsExchange FeatureClass.holeCap entries
      + classAbsExchange FeatureClass.crossSection entries
      + classAbsExchange FeatureClass.unroofPatch entries
      = totalAbsExchange entries := by
  induction entries with
  | nil =>
      simp [classAbsExchange, classEntries, subsetEntries, totalAbsExchange]
  | cons entry entries ih =>
      cases hclass : entry.feature.featureClass
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [classAbsExchange, classEntries, subsetEntries, totalAbsExchange,
          hclass, add_assoc, add_left_comm, add_comm] using hstep
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [classAbsExchange, classEntries, subsetEntries, totalAbsExchange,
          hclass, add_assoc, add_left_comm, add_comm] using hstep
      · have hstep := congrArg (fun t => entry.absFlux + t) ih
        simpa [classAbsExchange, classEntries, subsetEntries, totalAbsExchange,
          hclass, add_assoc, add_left_comm, add_comm] using hstep

end Stent
