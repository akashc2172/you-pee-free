"""Tests for COMSOL automation components."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.comsol.result_parser import COMSOLResult, ResultParser
from src.comsol.runner import COMSOLRunner
from src.comsol.hole_flux import (
    build_shaft_hole_flux_targets,
    merge_flux_with_targets,
    parse_shaft_hole_flux_csv,
)
from src.comsol.flux_extraction import summarize_flux_outputs
from src.cad.stent_generator import StentGenerator, StentParameters


def _write_realized_geometry(path: Path) -> None:
    path.write_text(
        "realized_n_prox,realized_n_mid,realized_n_dist,realized_midsection_hole_count\n"
        "1,2,1,2\n"
    )


def _write_hole_sidecar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "hole_metadata_sidecar_v2",
                "design_id": path.stem,
                "frame_definition": {"units": "mm"},
                "holes": [],
            }
        )
    )


def _write_measurement_sidecar(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "measurement_surface_sidecar_v1",
                "design_id": path.stem,
                "units": "mm",
                "frame_definition": {"units": "mm"},
                "features": [
                    {
                        "feature_id": "sec_inlet_ref",
                        "feature_class": "pressure_ref",
                        "zone": "prox",
                        "geometry_type": "named_selection",
                        "selection_tag": "inlet",
                    }
                ],
            }
        )
    )


def _write_results_csv(
    path: Path,
    *,
    q_out: float = 100.5,
    delta_p: float = 490.0,
    q_in: float = -100.0,
    p_in: float = 490.0,
    p_out: float = 0.0,
    mass_balance_error: float = 0.005,
    mesh_min_quality: float = 0.12,
    solver_relative_tolerance: float | None = 1e-4,
    extra_metrics: dict[str, float] | None = None,
) -> None:
    headers = [
        "q_out",
        "delta_p",
        "q_in",
        "p_in",
        "p_out",
        "mass_balance_error",
        "mesh_min_quality",
    ]
    values = [
        q_out,
        delta_p,
        q_in,
        p_in,
        p_out,
        mass_balance_error,
        mesh_min_quality,
    ]
    if solver_relative_tolerance is not None:
        headers.append("solver_relative_tolerance")
        values.append(solver_relative_tolerance)
    if extra_metrics:
        for key, value in extra_metrics.items():
            headers.append(key)
            values.append(value)
    path.write_text(",".join(headers) + "\n" + ",".join(str(v) for v in values) + "\n")


def _write_log(
    path: Path,
    *,
    converged: bool = True,
    include_relative_tolerance: bool = True,
) -> None:
    lines = [
        "Minimum element quality: 0.12",
        "Solution time: 12.5 s",
    ]
    if include_relative_tolerance:
        lines.append("Relative tolerance: 1e-4")
    if converged:
        lines.extend(
            [
                "Stationary Solver 1 in Study 1/Solution 1 (sol1)",
                "Ended at Mar 11, 2026, 7:35:36 PM.",
            ]
        )
    path.write_text("\n".join(lines))


def _write_template_contract(base_mph: Path, **overrides: object) -> None:
    payload = {
        "schema_version": "comsol_template_contract_v1",
        "template_id": "base_flow_v1",
        "template_version": "2026-03-12",
        "parser_expectations_version": "comsol_parser_expectations_v1",
        "sim_contract_version": "v1_deltaP490_steady_laminar",
        "domain_template": "triple_domain_dumbbell",
        "selection_strategy": "coordinate_bbox",
        "pressure_contract": {
            "mode": "pressure_driven",
            "p_inlet_pa": 490.0,
            "p_outlet_pa": 0.0,
            "delta_p_pa": 490.0,
        },
        "required_named_selections": [
            "inlet",
            "outlet",
            "stent_walls",
            "coil_zone",
            "mid_zone",
        ],
        "required_exports": [
            "results_csv",
            "realized_geometry_csv",
        ],
        "artifact_filenames": {
            "results_csv": "{run_id}_results.csv",
            "realized_geometry_csv": "{run_id}_realized_geometry.csv",
            "batch_log": "{run_id}.log",
        },
    }
    payload.update(overrides)
    base_mph.with_suffix(".contract.json").write_text(json.dumps(payload))


def _valid_result(run_id: str) -> COMSOLResult:
    return COMSOLResult(
        run_id=run_id,
        run_status="valid",
        failure_class="",
        converged=True,
        convergence_evidence=True,
        q_out=1.0,
        q_in=-1.0,
        delta_p=490.0,
        p_in=490.0,
        p_out=0.0,
        mass_imbalance=0.0,
        mesh_min_quality=0.2,
        solver_relative_tolerance=1e-4,
        realized_geometry_present=True,
        realized_geometry={"realized_midsection_hole_count": 2},
        qc_passed=True,
    )


def _simulation_contract(max_retries: int = 1) -> dict:
    return {
        "sim_contract_version": "v1_deltaP490_steady_laminar",
        "domain_template": "triple_domain_dumbbell",
        "selection_strategy": "coordinate_bbox",
        "boundary_conditions": {
            "p_inlet_pa": 490.0,
            "p_outlet_pa": 0.0,
            "delta_p_pa": 490.0,
        },
        "failure_policy": {"max_remesh_retries": max_retries},
    }


class TestResultParser:
    def test_parse_success(self, tmp_path: Path):
        run_id = "design_001"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv")
        _write_log(d / f"{run_id}.log")
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "valid"
        assert result.qc_passed is True
        assert result.realized_geometry_present is True
        assert result.realized_geometry["realized_midsection_hole_count"] == 2

    def test_missing_convergence_evidence_fails_solver(self, tmp_path: Path):
        run_id = "missing_conv"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv")
        _write_log(d / f"{run_id}.log", converged=False)
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "failed_solver"
        assert result.failure_class == "missing_convergence_evidence"

    def test_missing_solver_tolerance_fails_closed(self, tmp_path: Path):
        run_id = "missing_tol"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv", solver_relative_tolerance=None)
        _write_log(d / f"{run_id}.log", include_relative_tolerance=False)
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "invalid_qc"
        assert "missing_solver_tolerance" in result.qc_fail_reasons

    def test_delta_p_mismatch_fails_qc(self, tmp_path: Path):
        run_id = "wrong_dp"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv", delta_p=500.5)
        _write_log(d / f"{run_id}.log")
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "invalid_qc"
        assert "delta_p_mismatch" in result.qc_fail_reasons

    def test_bad_flow_sign_fails_qc(self, tmp_path: Path):
        run_id = "bad_flow"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv", q_in=100.0, q_out=100.0)
        _write_log(d / f"{run_id}.log")
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "invalid_qc"
        assert "flow_sign_inconsistent" in result.qc_fail_reasons

    def test_missing_realized_geometry_blocks_valid(self, tmp_path: Path):
        run_id = "missing_realized"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv")
        _write_log(d / f"{run_id}.log")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.run_status == "failed_extraction"
        assert result.failure_class == "missing_realized_geometry"


def test_summarize_flux_outputs_builds_summary_metrics():
    scalars_df = pd.DataFrame(
        [
            {
                "design_id": "design_0000",
                "p_ramp": 1.0,
                "Q_in_ml_min": -120.0,
                "Q_out_ml_min": 118.0,
                "p_in_avg_Pa": 490.0,
                "p_out_avg_Pa": 0.0,
                "Q_lumen_out_ml_min": 80.0,
                "Q_annulus_out_ml_min": 38.0,
                "max_vel_m_s": 0.25,
                "max_p_Pa": 492.0,
                "min_p_Pa": -2.0,
                "stent_length_mm": 140.0,
            }
        ]
    )
    features_df = pd.DataFrame(
        [
            {
                "design_id": "design_0000",
                "p_ramp": 1.0,
                "feature_id": "cap_hole_shaft_prox_000",
                "feature_class": "hole_cap",
                "zone": "prox",
                "parent_feature": "shaft_prox_000",
                "source_type": "shaft",
                "axial_x_mm": 10.0,
                "open_length_mm": pd.NA,
                "signed_flux_ml_min": 3.0,
                "abs_flux_ml_min": 3.0,
            },
            {
                "design_id": "design_0000",
                "p_ramp": 1.0,
                "feature_id": "cap_hole_shaft_mid_000",
                "feature_class": "hole_cap",
                "zone": "mid",
                "parent_feature": "shaft_mid_000",
                "source_type": "shaft",
                "axial_x_mm": 40.0,
                "open_length_mm": pd.NA,
                "signed_flux_ml_min": -1.0,
                "abs_flux_ml_min": 1.0,
            },
            {
                "design_id": "design_0000",
                "p_ramp": 1.0,
                "feature_id": "patch_unroof_1",
                "feature_class": "unroof_patch",
                "zone": "dist",
                "parent_feature": "",
                "source_type": "",
                "axial_x_mm": 135.0,
                "open_length_mm": 12.0,
                "signed_flux_ml_min": -4.0,
                "abs_flux_ml_min": 4.0,
            },
        ]
    )

    summary_df = summarize_flux_outputs("design_0000", scalars_df, features_df)
    row = summary_df.iloc[0]

    assert row["deltaP_Pa"] == pytest.approx(490.0)
    assert row["conductance_ml_min_per_Pa"] == pytest.approx(118.0 / 490.0)
    assert row["Q_holes_net_ml_min"] == pytest.approx(2.0)
    assert row["Q_holes_abs_ml_min"] == pytest.approx(4.0)
    assert row["Q_unroof_abs_ml_min"] == pytest.approx(4.0)
    assert row["n_active_holes"] == 2
    assert row["prox_hole_abs_flux_ml_min"] == pytest.approx(3.0)
    assert row["mid_hole_abs_flux_ml_min"] == pytest.approx(1.0)
    assert row["frac_lumen_out"] == pytest.approx(80.0 / 118.0)
    assert row["frac_unroof_of_exchange_total"] == pytest.approx(0.5)
    assert row["hole_uniformity_gini"] == pytest.approx(0.25)
    assert row["exchange_number"] == pytest.approx(8.0 / 118.0)
    assert row["hole_only_exchange_number"] == pytest.approx(4.0 / 118.0)
    assert row["net_direction_index"] == pytest.approx(0.5)
    assert row["hole_flux_centroid_x_mm"] == pytest.approx(17.5)
    assert row["hole_flux_spread_x_mm"] == pytest.approx(12.9903810568)
    assert row["hole_flux_dominance_ratio"] == pytest.approx(1.5)
    assert row["invariants_passed"] == 1
    assert row["invariant_warnings"] == ""
    assert row["Q_hole_shaft_prox_000_ml_min"] == pytest.approx(3.0)
    assert row["absQ_hole_shaft_mid_000_ml_min"] == pytest.approx(1.0)


def test_summarize_flux_outputs_emits_invariant_warnings_for_bad_feature_rows():
    scalars_df = pd.DataFrame(
        [
            {
                "design_id": "design_0001",
                "p_ramp": 1.0,
                "Q_in_ml_min": -20.0,
                "Q_out_ml_min": 20.0,
                "p_in_avg_Pa": 490.0,
                "p_out_avg_Pa": 0.0,
                "Q_lumen_out_ml_min": 12.0,
                "Q_annulus_out_ml_min": 8.0,
            }
        ]
    )
    features_df = pd.DataFrame(
        [
            {
                "design_id": "design_0001",
                "p_ramp": 1.0,
                "feature_id": "cap_hole_shaft_mid_000",
                "feature_class": "hole_cap",
                "zone": "mid",
                "parent_feature": "shaft_mid_000",
                "source_type": "shaft",
                "axial_x_mm": 40.0,
                "signed_flux_ml_min": 2.0,
                "abs_flux_ml_min": 1.0,
            },
            {
                "design_id": "design_0001",
                "p_ramp": 1.0,
                "feature_id": "cap_hole_shaft_mid_000",
                "feature_class": "hole_cap",
                "zone": "mid",
                "parent_feature": "shaft_mid_001",
                "source_type": "shaft",
                "axial_x_mm": 45.0,
                "signed_flux_ml_min": -0.5,
                "abs_flux_ml_min": 0.5,
            },
        ]
    )

    summary_df = summarize_flux_outputs("design_0001", scalars_df, features_df)
    row = summary_df.iloc[0]

    assert row["invariants_passed"] == 0
    assert "duplicate_feature_ids" in row["invariant_warnings"]
    assert "hole_abs_lt_signed_magnitude" in row["invariant_warnings"]

def test_grouped_hole_metrics_are_derived_downstream(tmp_path: Path):
    run_id = "grouped_holes"
    d = tmp_path / run_id
    d.mkdir()
    _write_results_csv(
        d / f"{run_id}_results.csv",
        q_out=120.0,
        extra_metrics={
            "q_sh_prox": 10.0,
            "q_sh_mid": 20.0,
            "q_sh_dist": 30.0,
            "wss_max": 4.5,
            "wss_p95_global": 2.5,
            "wss_p99_global": 3.5,
        },
    )
    _write_log(d / f"{run_id}.log")
    _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

    parser = ResultParser()
    result = parser.parse_run(d, run_id)

    assert result.run_status == "valid"
    assert result.q_sh_total_signed == pytest.approx(60.0)
    assert result.q_sh_total_abs == pytest.approx(60.0)
    assert result.hole_uniformity_cv_grouped == pytest.approx(0.40824829, rel=1e-6)
    assert result.hole_uniformity_maxmin_grouped == pytest.approx(3.0)
    assert result.fraction_partition_lumen == pytest.approx(120.0 / 180.0)
    assert result.fraction_partition_holes == pytest.approx(60.0 / 180.0)
    assert result.wss_max == pytest.approx(4.5)
    assert result.wss_p95_global == pytest.approx(2.5)
    assert result.wss_p99_global == pytest.approx(3.5)


class TestCOMSOLRunner:
    def test_template_contract_report_valid_when_schema_matches(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )

        report = runner.inspect_template_contract()

        assert report["valid"] is True
        assert report["error"] == ""

    def test_template_contract_missing_fails_closed(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )

        record = runner.run_batch(design_id="d1", parameters={}, cad_file=cad_file)

        assert record["run_status"] == "failed_geometry"
        assert record["failure_class"] == "failed_selection"

    def test_template_contract_mismatch_fails_closed(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph, selection_strategy="entity_id")
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )

        record = runner.run_batch(design_id="d1", parameters={}, cad_file=cad_file)

        assert record["run_status"] == "failed_geometry"
        assert record["failure_class"] == "failed_selection"

    def test_undeclared_runtime_params_are_rejected(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )

        record = runner.run_batch(
            design_id="d1",
            parameters={"realized_arc_positions": "[0, 90]"},
            cad_file=cad_file,
        )

        assert record["run_status"] == "failed_geometry"
        assert record["failure_class"] == "invalid_runtime_parameters"

    def test_unsafe_runtime_values_are_rejected(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )

        record = runner.run_batch(
            design_id="d1",
            parameters={"p_inlet_pa": "490,0"},
            cad_file=cad_file,
        )

        assert record["run_status"] == "failed_geometry"
        assert record["failure_class"] == "invalid_runtime_parameters"

    @patch("subprocess.run")
    def test_manifest_metadata_does_not_leak_into_comsol_params(
        self,
        mock_subprocess_run,
        tmp_path: Path,
    ):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        hole_metadata_file = tmp_path / "design.holes.json"
        hole_metadata_file.write_text("{}")
        measurement_metadata_file = tmp_path / "design.meters.json"
        _write_measurement_sidecar(measurement_metadata_file)
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["comsol"],
            returncode=0,
            stdout="",
            stderr="",
        )

        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )
        manifest = pd.DataFrame(
            [
                {
                    "design_id": "design_0001",
                    "cad_file": str(cad_file),
                    "requested_hole_positions": "[1,2,3]",
                    "realized_arc_positions": "[0,90]",
                    "hole_metadata_file": str(hole_metadata_file),
                    "measurement_metadata_file": str(measurement_metadata_file),
                    "run_status": "pending_simulation",
                    "failure_class": "",
                    "sim_contract_version": "wrong_manifest_value",
                }
            ]
        )

        with patch.object(runner.result_parser, "parse_run", return_value=_valid_result("design_0001")):
            out_df = runner.run_manifest(manifest, checkpoint_path=tmp_path / "checkpoint.csv")

        assert out_df.loc[0, "run_status"] == "valid"
        cmd = mock_subprocess_run.call_args[0][0]
        pnames = cmd[cmd.index("-pname") + 1].split(",")
        assert pnames == [
            "cad_path",
            "hole_metadata_path",
            "measurement_metadata_path",
            "design_id",
            "p_inlet_pa",
            "p_outlet_pa",
            "delta_p_pa",
            "mesh_retry_level",
            "sim_contract_version",
            "domain_template",
            "selection_strategy",
        ]
        assert "requested_hole_positions" not in pnames
        assert "realized_arc_positions" not in pnames
        assert "run_status" not in pnames

    def test_missing_hole_metadata_fails_runtime_params(self, tmp_path: Path):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        _write_measurement_sidecar(cad_file.with_suffix(".meters.json"))

        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(),
        )
        record = runner.run_batch(design_id="d1", parameters={}, cad_file=cad_file)

        assert record["run_status"] == "failed_geometry"
        assert record["failure_class"] == "invalid_runtime_parameters"


class TestHoleFluxUtilities:
    def test_build_shaft_hole_flux_targets_from_sidecar(self, tmp_path: Path):
        params = StentParameters(n_prox=1, n_mid=2, n_dist=1)
        gen = StentGenerator(params)
        step_path = tmp_path / "design_0000.step"
        gen.export_step(step_path)

        targets = build_shaft_hole_flux_targets(step_path.with_suffix(".holes.json"))

        assert len(targets) == params.realized_body_holes
        assert set(targets["type"]) == {"shaft"}
        assert all(name.startswith("CP_shaft_") for name in targets["cut_plane_name"])
        assert list(targets["axial_rank"]) == sorted(targets["axial_rank"])

    def test_parse_and_merge_wide_flux_csv(self, tmp_path: Path):
        params = StentParameters(n_prox=1, n_mid=1, n_dist=1)
        gen = StentGenerator(params)
        step_path = tmp_path / "design_0001.step"
        gen.export_step(step_path)

        targets = build_shaft_hole_flux_targets(step_path.with_suffix(".holes.json"))
        flux_row = {"p_ramp": 1.0}
        for _, target in targets.iterrows():
            flux_row[target["signed_dv_name"]] = float(target["axial_rank"]) + 0.1
            flux_row[target["abs_dv_name"]] = float(target["axial_rank"]) + 1.1
        flux_csv = tmp_path / "per_hole_flux.csv"
        pd.DataFrame([flux_row]).to_csv(flux_csv, index=False)

        parsed = parse_shaft_hole_flux_csv(flux_csv)
        merged = merge_flux_with_targets(step_path.with_suffix(".holes.json"), flux_csv)

        assert len(parsed) == len(targets)
        assert len(merged) == len(targets)
        assert "signed_flux_m3s" in merged.columns
        assert "abs_flux_m3s" in merged.columns
        assert merged["p_ramp"].iloc[0] == pytest.approx(1.0)

    @patch("subprocess.run")
    def test_attempts_are_attempt_scoped_and_parser_reads_current_attempt_only(
        self,
        mock_subprocess_run,
        tmp_path: Path,
    ):
        base_mph = tmp_path / "base.mph"
        base_mph.touch()
        _write_template_contract(base_mph)
        cad_file = tmp_path / "design.step"
        cad_file.write_text("dummy")
        _write_hole_sidecar(cad_file.with_suffix(".holes.json"))
        _write_measurement_sidecar(cad_file.with_suffix(".meters.json"))
        mock_subprocess_run.return_value = subprocess.CompletedProcess(
            args=["comsol"],
            returncode=0,
            stdout="",
            stderr="",
        )

        runner = COMSOLRunner(
            base_mph=base_mph,
            output_dir=tmp_path / "out",
            simulation_contract=_simulation_contract(max_retries=1),
        )
        first = COMSOLResult(
            run_id="d1",
            run_status="invalid_qc",
            failure_class="invalid_qc",
            converged=True,
            convergence_evidence=True,
            q_out=1.0,
            q_in=-1.0,
            delta_p=490.0,
            p_in=490.0,
            p_out=0.0,
            mass_imbalance=0.0,
            mesh_min_quality=0.01,
            solver_relative_tolerance=1e-4,
            realized_geometry_present=True,
            qc_fail_reasons=["mesh_quality_below_threshold"],
        )
        second = _valid_result("d1")

        with patch.object(runner.result_parser, "parse_run", side_effect=[first, second]) as mock_parse:
            record = runner.run_batch(design_id="d1", parameters={}, cad_file=cad_file)

        first_dir = mock_parse.call_args_list[0].args[0]
        second_dir = mock_parse.call_args_list[1].args[0]
        assert str(first_dir).endswith("attempt_0")
        assert str(second_dir).endswith("attempt_1")
        assert record["selected_attempt"] == "attempt_1"
        assert "attempt_1" in record["parsed_results_file"]

    def test_per_hole_flux_csv_ingested_when_present(self, tmp_path: Path):
        run_id = "design_flux"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv")
        _write_log(d / f"{run_id}.log")
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        flux_csv = d / f"{run_id}_shaft_hole_flux.csv"
        flux_csv.write_text(
            "hole_id,axial_x_mm,region,type,p_ramp,signed_flux_m3s,abs_flux_m3s\n"
            "shaft_prox_000,1.0,prox,shaft,1.0,1.23e-11,1.23e-11\n"
            "shaft_prox_001,4.6,prox,shaft,1.0,2.34e-11,2.34e-11\n"
        )

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.per_hole_flux_csv_found is True
        assert result.per_hole_flux_count == 2

    def test_per_hole_flux_csv_absent_is_fine(self, tmp_path: Path):
        run_id = "design_noflux"
        d = tmp_path / run_id
        d.mkdir()
        _write_results_csv(d / f"{run_id}_results.csv")
        _write_log(d / f"{run_id}.log")
        _write_realized_geometry(d / f"{run_id}_realized_geometry.csv")

        parser = ResultParser()
        result = parser.parse_run(d, run_id)

        assert result.per_hole_flux_csv_found is False
        assert result.per_hole_flux_count == 0
        assert result.run_status == "valid"


class TestNamingContractAlignment:
    """Verify Java source naming patterns match Python constants."""

    def test_java_source_tag_patterns_match_python(self):
        java_source = Path(__file__).parent.parent / "java" / "BuildShaftHoleFluxLayer.java.txt"
        if not java_source.exists():
            pytest.skip("Java source not found")

        content = java_source.read_text()

        # Verify tag patterns from hole_flux.py are present in Java source
        assert "CP_" in content, "Java source must use CP_ prefix for cut planes"
        assert "DV_hole_" in content, "Java source must use DV_hole_ prefix for derived values"
        assert "_signed" in content, "Java source must use _signed suffix"
        assert "_abs" in content, "Java source must use _abs suffix"

        # Verify CSV column names match parser expectations
        assert "hole_id" in content, "Java source must emit hole_id column"
        assert "signed_flux_m3s" in content, "Java source must emit signed_flux_m3s column"
        assert "abs_flux_m3s" in content, "Java source must emit abs_flux_m3s column"
        assert "p_ramp" in content, "Java source must emit p_ramp column"
        assert "axial_x_mm" in content, "Java source must emit axial_x_mm column"

    def test_java_source_does_not_use_model_param_get(self):
        """Lesson #1/#19: model.param().get() is wrong for string paths."""
        java_source = Path(__file__).parent.parent / "java" / "BuildShaftHoleFluxLayer.java.txt"
        if not java_source.exists():
            pytest.skip("Java source not found")

        content = java_source.read_text()
        assert "model.param().get(" not in content, (
            "Java source must NOT use model.param().get() — "
            "COMSOL Parameters treat values as numeric expressions"
        )

    def test_java_source_does_not_use_anonymous_comparators(self):
        """Lesson #3: COMSOL method editor chokes on anonymous comparators."""
        java_source = Path(__file__).parent.parent / "java" / "BuildShaftHoleFluxLayer.java.txt"
        if not java_source.exists():
            pytest.skip("Java source not found")

        content = java_source.read_text()
        assert "new java.util.Comparator" not in content, (
            "Java source must NOT use anonymous Comparator classes — "
            "COMSOL method editor rejects them"
        )

    def test_flux_extraction_java_source_has_column_fallback_for_sweeps(self):
        java_source = Path(__file__).parent.parent / "java" / "BuildFluxExtractionLayer.java.txt"
        if not java_source.exists():
            pytest.skip("Java source not found")

        content = java_source.read_text()

        assert "useColumnFallback" in content, (
            "BuildFluxExtractionLayer must support fallback snapshot iteration "
            "when SolutionInfo outer solutions are unavailable"
        )
        assert "fallbackSnapshotCount" in content, (
            "BuildFluxExtractionLayer must infer fallback snapshot count from getReal() output"
        )
        assert "columnIndex" in content, (
            "BuildFluxExtractionLayer must track the active fallback column index"
        )
        assert "vals[0][columnIndex]" in content, (
            "BuildFluxExtractionLayer must read per-snapshot values by column in fallback mode"
        )
