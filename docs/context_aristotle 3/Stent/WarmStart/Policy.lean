import Stent.WarmStart.Distance

namespace Stent.WarmStart

structure Anchor where
  anchorId : Nat
  design : DesignVector

noncomputable def anchorScore (cfg : DistanceConfig) (target : DesignVector) (anchor : Anchor) : ℝ :=
  score cfg target anchor.design

noncomputable def chooseBetter (cfg : DistanceConfig) (target : DesignVector) (left right : Anchor) : Anchor :=
  if hlt : anchorScore cfg target left < anchorScore cfg target right then
    left
  else if hgt : anchorScore cfg target right < anchorScore cfg target left then
    right
  else if left.anchorId ≤ right.anchorId then
    left
  else
    right

noncomputable def selectNearestCore (cfg : DistanceConfig) (target : DesignVector) (best : Anchor) :
    List Anchor → Anchor
  | [] => best
  | anchor :: anchors => selectNearestCore cfg target (chooseBetter cfg target best anchor) anchors

noncomputable def selectNearest? (cfg : DistanceConfig) (target : DesignVector) :
    List Anchor → Option Anchor
  | [] => none
  | anchor :: anchors => some (selectNearestCore cfg target anchor anchors)

theorem chooseBetter_eq_left_or_right
    (cfg : DistanceConfig) (target : DesignVector) (left right : Anchor) :
    chooseBetter cfg target left right = left ∨ chooseBetter cfg target left right = right := by
  unfold chooseBetter
  split
  · simp
  · split
    · simp
    · split <;> simp

theorem selectNearest?_isSome_of_nonempty
    (cfg : DistanceConfig) (target : DesignVector) (anchors : List Anchor)
    (h : anchors ≠ []) :
    (selectNearest? cfg target anchors).isSome := by
  cases anchors with
  | nil => contradiction
  | cons anchor anchors =>
      simp [selectNearest?]

theorem selectNearestCore_mem
    (cfg : DistanceConfig) (target : DesignVector) (best : Anchor) (anchors : List Anchor) :
    selectNearestCore cfg target best anchors ∈ best :: anchors := by
  induction anchors generalizing best with
  | nil =>
      simp [selectNearestCore]
  | cons anchor anchors ih =>
      have hchoice :
          chooseBetter cfg target best anchor = best
            ∨ chooseBetter cfg target best anchor = anchor :=
        chooseBetter_eq_left_or_right cfg target best anchor
      cases hchoice with
      | inl hbest =>
          have hmem : selectNearestCore cfg target best anchors ∈ best :: anchors := ih best
          rw [selectNearestCore, hbest]
          have hmem' :
              selectNearestCore cfg target best anchors = best
                ∨ selectNearestCore cfg target best anchors ∈ anchors := by
            simpa using hmem
          cases hmem' with
          | inl hEq =>
              simp [List.mem_cons, hEq]
          | inr htail =>
              simp [List.mem_cons, htail]
      | inr hanchor =>
          have : selectNearestCore cfg target anchor anchors ∈ anchor :: anchors := by
            simpa [selectNearestCore, hanchor] using ih anchor
          rw [selectNearestCore, hanchor]
          have hmem' :
              selectNearestCore cfg target anchor anchors = anchor
                ∨ selectNearestCore cfg target anchor anchors ∈ anchors := by
            simpa using this
          cases hmem' with
          | inl hEq =>
              simp [List.mem_cons, hEq]
          | inr htail =>
              simp [List.mem_cons, htail]

theorem selectNearest?_mem
    (cfg : DistanceConfig) (target : DesignVector) (anchors : List Anchor) (anchor : Anchor)
    (hsel : selectNearest? cfg target anchors = some anchor) :
    anchor ∈ anchors := by
  cases anchors with
  | nil =>
      simp [selectNearest?] at hsel
  | cons head tail =>
      simp [selectNearest?] at hsel
      subst hsel
      exact selectNearestCore_mem cfg target head tail

theorem chooseBetter_tie_break
    (cfg : DistanceConfig) (target : DesignVector) (left right : Anchor)
    (hscore : anchorScore cfg target left = anchorScore cfg target right)
    (hid : left.anchorId ≤ right.anchorId) :
    chooseBetter cfg target left right = left := by
  unfold chooseBetter
  have hnotlt : ¬ anchorScore cfg target left < anchorScore cfg target right := by
    simpa [hscore]
  have hnotgt : ¬ anchorScore cfg target right < anchorScore cfg target left := by
    simpa [hscore]
  simp [hnotlt, hnotgt, hid]

inductive CheckpointClass
  | near95
  | medium75
  | coldStart
  | topologyReset
  deriving DecidableEq, Repr

structure CheckpointThresholds where
  near : ℝ
  medium : ℝ
  ordered : near ≤ medium

noncomputable def checkpointPolicy (thresholds : CheckpointThresholds) (topologyCompatible : Bool) (distance : ℝ) :
    CheckpointClass :=
  if !topologyCompatible then
    CheckpointClass.topologyReset
  else if distance ≤ thresholds.near then
    CheckpointClass.near95
  else if distance ≤ thresholds.medium then
    CheckpointClass.medium75
  else
    CheckpointClass.coldStart

theorem checkpointPolicy_of_incompatible
    (thresholds : CheckpointThresholds) (distance : ℝ) :
    checkpointPolicy thresholds false distance = CheckpointClass.topologyReset := by
  simp [checkpointPolicy]

theorem checkpointPolicy_of_near
    (thresholds : CheckpointThresholds) (distance : ℝ)
    (hnear : distance ≤ thresholds.near) :
    checkpointPolicy thresholds true distance = CheckpointClass.near95 := by
  simp [checkpointPolicy, hnear]

theorem checkpointPolicy_of_medium
    (thresholds : CheckpointThresholds) (distance : ℝ)
    (hgt : thresholds.near < distance)
    (hmed : distance ≤ thresholds.medium) :
    checkpointPolicy thresholds true distance = CheckpointClass.medium75 := by
  have hnotnear : ¬ distance ≤ thresholds.near := by linarith
  simp [checkpointPolicy, hnotnear, hmed]

theorem checkpointPolicy_of_far
    (thresholds : CheckpointThresholds) (distance : ℝ)
    (hfar : thresholds.medium < distance) :
    checkpointPolicy thresholds true distance = CheckpointClass.coldStart := by
  have hnotnear : ¬ distance ≤ thresholds.near := by linarith [thresholds.ordered, hfar]
  have hnotmed : ¬ distance ≤ thresholds.medium := by linarith
  simp [checkpointPolicy, hnotnear, hnotmed]

theorem checkpointPolicy_total
    (thresholds : CheckpointThresholds) (topologyCompatible : Bool) (distance : ℝ) :
    checkpointPolicy thresholds topologyCompatible distance = CheckpointClass.near95
      ∨ checkpointPolicy thresholds topologyCompatible distance = CheckpointClass.medium75
      ∨ checkpointPolicy thresholds topologyCompatible distance = CheckpointClass.coldStart
      ∨ checkpointPolicy thresholds topologyCompatible distance = CheckpointClass.topologyReset := by
  cases topologyCompatible <;> by_cases hnear : distance ≤ thresholds.near <;>
      by_cases hmed : distance ≤ thresholds.medium <;>
      simp [checkpointPolicy, hnear, hmed]

end Stent.WarmStart
