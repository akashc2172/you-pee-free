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


def _write_realized_geometry(path: Path) -> None:
    path.write_text(
        "realized_n_prox,realized_n_mid,realized_n_dist,realized_midsection_hole_count\n"
        "1,2,1,2\n"
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
