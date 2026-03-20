import Mathlib.Data.Real.Basic

namespace Stent

inductive Zone
  | prox
  | mid
  | dist
  deriving DecidableEq, Repr

inductive FeatureClass
  | holeCap
  | crossSection
  | unroofPatch
  deriving DecidableEq, Repr

inductive SourceType
  | shaft
  | coil
  | none
  deriving DecidableEq, Repr

structure FeatureId where
  val : Nat
  deriving DecidableEq, Repr

structure Feature where
  id : FeatureId
  featureClass : FeatureClass
  zone : Zone
  parentFeature : Option FeatureId := none
  sourceType : Option SourceType := none
  axialX : ℝ
  openLength : Option ℝ := none
  normalizedX : Option ℝ := none

def Zone.all : List Zone := [Zone.prox, Zone.mid, Zone.dist]

def FeatureClass.all : List FeatureClass :=
  [FeatureClass.holeCap, FeatureClass.crossSection, FeatureClass.unroofPatch]

end Stent
