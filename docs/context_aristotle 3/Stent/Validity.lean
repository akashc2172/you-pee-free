import Stent.Objectives

namespace Stent

inductive EvalStatus
  | ok
  | empty
  | exception
  | nonfinite
  deriving DecidableEq, Repr

structure RawSample where
  pressureIn? : Option ℝ
  pressureOut? : Option ℝ
  qOut? : Option ℝ
  features : List FeatureFlux
  requiredStatuses : List EvalStatus
  massBalanceResidual : ℝ
  centroid? : Option ℝ := none
  spread? : Option ℝ := none

structure ValidityConfig where
  residualTol : ℝ
  residualTol_nonneg : 0 ≤ residualTol := by positivity

def CoreFieldsPresent (sample : RawSample) : Prop :=
  sample.pressureIn?.isSome ∧ sample.pressureOut?.isSome ∧ sample.qOut?.isSome

def RequiredStatusesOk (sample : RawSample) : Prop :=
  ∀ status ∈ sample.requiredStatuses, status = EvalStatus.ok

def ValidSample (cfg : ValidityConfig) (sample : RawSample) : Prop :=
  CoreFieldsPresent sample
    ∧ RequiredStatusesOk sample
    ∧ |sample.massBalanceResidual| ≤ cfg.residualTol

theorem ValidSample.coreFields
    {cfg : ValidityConfig} {sample : RawSample}
    (hvalid : ValidSample cfg sample) :
    CoreFieldsPresent sample := hvalid.1

theorem ValidSample.requiredStatusesOk
    {cfg : ValidityConfig} {sample : RawSample}
    (hvalid : ValidSample cfg sample) :
    RequiredStatusesOk sample := hvalid.2.1

theorem ValidSample.massBalanceBound
    {cfg : ValidityConfig} {sample : RawSample}
    (hvalid : ValidSample cfg sample) :
    |sample.massBalanceResidual| ≤ cfg.residualTol := hvalid.2.2

def derivedOutputs? (sample : RawSample) : Option AggregateOutputs :=
  match sample.pressureIn?, sample.pressureOut?, sample.qOut? with
  | some pIn, some pOut, some qOut =>
      some
        { pressureDrop := pressureDrop pIn pOut
          qOut := qOut
          exchangeTotal := totalExchangeMetric sample.features
          centroid := sample.centroid?
          spread := sample.spread? }
  | _, _, _ => none

theorem derivedOutputs?_isSome_of_valid
    {cfg : ValidityConfig} {sample : RawSample}
    (hvalid : ValidSample cfg sample) :
    (derivedOutputs? sample).isSome := by
  rcases hvalid.1 with ⟨hIn, hOut, hQ⟩
  rcases Option.isSome_iff_exists.mp hIn with ⟨pIn, hpIn⟩
  rcases Option.isSome_iff_exists.mp hOut with ⟨pOut, hpOut⟩
  rcases Option.isSome_iff_exists.mp hQ with ⟨qOut, hqOut⟩
  simp [derivedOutputs?, hpIn, hpOut, hqOut]

end Stent
