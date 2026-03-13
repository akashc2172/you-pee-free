"""
COMSOL Result Parser.
Parses simulation output CSVs and solver logs, then evaluates run-level QC gates.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.comsol.expectations import (
    CONVERGENCE_LOG_PATTERNS,
    DEFAULT_DELTA_P_ABS_TOLERANCE_PA,
    LOG_FILENAME_TEMPLATE,
    REALIZED_GEOMETRY_FILENAME_TEMPLATE,
    RESULT_COLUMN_ALIASES,
    RESULTS_FILENAME_TEMPLATE,
    TOLERANCE_LOG_PATTERNS,
    parser_expectations_snapshot,
)

DEFAULT_QC_THRESHOLDS: Dict[str, Any] = {
    "max_mass_balance_error": 0.01,
    "min_mesh_quality": 0.05,
    "max_solver_relative_tolerance": 1e-3,
    "delta_p_abs_tolerance_pa": DEFAULT_DELTA_P_ABS_TOLERANCE_PA,
    "require_finite_outputs": True,
    "require_pressure_sign_consistency": True,
    "require_flow_sign_consistency": True,
    "require_explicit_solver_tolerance": True,
    "require_realized_geometry": True,
}


@dataclass
class COMSOLResult:
    run_id: str
    run_status: str = "failed_extraction"
    failure_class: str = "failed_extraction"
    q_out: Optional[float] = None
    q_in: Optional[float] = None
    delta_p: Optional[float] = None
    p_in: Optional[float] = None
    p_out: Optional[float] = None
    converged: bool = False
    convergence_evidence: bool = False
    iterations: int = 0
    cpu_time_s: float = 0.0
    mass_imbalance: Optional[float] = None
    mesh_min_quality: Optional[float] = None
    solver_relative_tolerance: Optional[float] = None
    realized_geometry_present: bool = False
    qc_passed: bool = False
    qc_fail_reasons: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw_metrics: Dict[str, Any] = field(default_factory=dict)
    realized_geometry: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        out = asdict(self)
        out["qc_fail_reasons"] = "; ".join(self.qc_fail_reasons)
        out["errors"] = "; ".join(self.errors)
        for key, value in self.realized_geometry.items():
            out[key] = value
        return out


class ResultParser:
    """Parses COMSOL outputs from a single attempt directory."""

    def __init__(
        self,
        qc_thresholds: Optional[Dict[str, Any]] = None,
        expected_delta_p_pa: Optional[float] = 490.0,
    ):
        self.qc_thresholds = dict(DEFAULT_QC_THRESHOLDS)
        if qc_thresholds:
            self.qc_thresholds.update(qc_thresholds)
        self.expected_delta_p_pa = expected_delta_p_pa

    def expectations_snapshot(self) -> Dict[str, Any]:
        return parser_expectations_snapshot(self.qc_thresholds, self.expected_delta_p_pa)

    def parse_run(self, run_dir: Path, run_id: str) -> COMSOLResult:
        run_dir = Path(run_dir)
        result = COMSOLResult(run_id=run_id)

        results_file = run_dir / RESULTS_FILENAME_TEMPLATE.format(run_id=run_id)
        log_file = run_dir / LOG_FILENAME_TEMPLATE.format(run_id=run_id)
        realized_file = run_dir / REALIZED_GEOMETRY_FILENAME_TEMPLATE.format(run_id=run_id)

        if results_file.exists():
            try:
                self._parse_metrics(results_file, result)
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"metrics_parse_error: {exc}")
        else:
            result.errors.append(f"results_file_missing: {results_file.name}")

        if log_file.exists():
            try:
                self._parse_log(log_file, result)
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"log_parse_error: {exc}")
        else:
            result.errors.append(f"log_file_missing: {log_file.name}")

        if realized_file.exists():
            try:
                self._parse_realized_geometry(realized_file, result)
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"realized_geometry_parse_error: {exc}")
        elif bool(self.qc_thresholds.get("require_realized_geometry", True)):
            result.errors.append(f"realized_geometry_missing: {realized_file.name}")

        self._finalize_metrics(result)
        self._apply_qc(result)
        return result

    @staticmethod
    def _normalize_key(key: str) -> str:
        key = key.strip().lower()
        key = re.sub(r"[^a-z0-9]+", "_", key)
        return key.strip("_")

    def _parse_metrics(self, file_path: Path, result: COMSOLResult) -> None:
        df = pd.read_csv(file_path, comment="%")
        if df.empty:
            raise ValueError("empty_results_file")

        row = df.iloc[-1]
        normalized = {self._normalize_key(str(k)): v for k, v in row.items()}
        result.raw_metrics = normalized

        def maybe_float(*keys: str) -> Optional[float]:
            for key in keys:
                if key in normalized and pd.notna(normalized[key]):
                    return float(normalized[key])
            return None

        result.q_out = maybe_float(*RESULT_COLUMN_ALIASES["q_out"])
        result.q_in = maybe_float(*RESULT_COLUMN_ALIASES["q_in"])
        result.p_in = maybe_float(*RESULT_COLUMN_ALIASES["p_in"])
        result.p_out = maybe_float(*RESULT_COLUMN_ALIASES["p_out"])
        result.delta_p = maybe_float(*RESULT_COLUMN_ALIASES["delta_p"])
        if result.delta_p is None and result.p_in is not None and result.p_out is not None:
            result.delta_p = result.p_in - result.p_out

        result.mass_imbalance = maybe_float(*RESULT_COLUMN_ALIASES["mass_imbalance"])
        result.mesh_min_quality = maybe_float(*RESULT_COLUMN_ALIASES["mesh_min_quality"])
        result.solver_relative_tolerance = maybe_float(*RESULT_COLUMN_ALIASES["solver_relative_tolerance"])

    def _parse_log(self, file_path: Path, result: COMSOLResult) -> None:
        content = file_path.read_text(errors="ignore")

        result.convergence_evidence = any(
            re.search(pattern, content, flags=re.IGNORECASE | re.DOTALL)
            for pattern in CONVERGENCE_LOG_PATTERNS
        )
        result.converged = result.convergence_evidence

        time_matches = re.findall(
            r"Solution time:?\s*([\d\.Ee+-]+)",
            content,
            flags=re.IGNORECASE,
        )
        if time_matches:
            result.cpu_time_s = float(time_matches[-1])

        iter_matches = re.findall(r"^\s*(\d+)\s+", content, flags=re.MULTILINE)
        if iter_matches:
            result.iterations = max(int(value) for value in iter_matches)
        else:
            iter_match = re.search(
                r"Number of iterations:?\s*(\d+)",
                content,
                flags=re.IGNORECASE,
            )
            if iter_match:
                result.iterations = int(iter_match.group(1))

        quality_matches = re.findall(
            r"Minimum element quality:?\s*([\d\.Ee+-]+)",
            content,
            flags=re.IGNORECASE,
        )
        if quality_matches:
            quality_vals = [float(value) for value in quality_matches]
            result.mesh_min_quality = min(quality_vals)

        for pattern in TOLERANCE_LOG_PATTERNS:
            rel_tol_match = re.search(pattern, content, flags=re.IGNORECASE)
            if rel_tol_match:
                result.solver_relative_tolerance = float(rel_tol_match.group(1))
                break

        error_lines = [
            line.strip()
            for line in content.splitlines()
            if "error:" in line.lower()
        ]
        if error_lines:
            result.errors.extend(error_lines)

    def _parse_realized_geometry(self, file_path: Path, result: COMSOLResult) -> None:
        df = pd.read_csv(file_path, comment="%")
        if df.empty:
            return

        row = df.iloc[-1]
        for key, value in row.items():
            norm = self._normalize_key(str(key))
            if norm.startswith("realized_") and pd.notna(value):
                result.realized_geometry[norm] = value

        if result.realized_geometry:
            result.realized_geometry_present = True

    @staticmethod
    def _is_present(value: Optional[float]) -> bool:
        return value is not None and pd.notna(value)

    @staticmethod
    def _is_finite(value: Optional[float]) -> bool:
        return value is not None and pd.notna(value) and math.isfinite(float(value))

    def _finalize_metrics(self, result: COMSOLResult) -> None:
        if result.mass_imbalance is None and self._is_finite(result.q_in) and self._is_finite(result.q_out):
            denom = max(abs(float(result.q_in)), abs(float(result.q_out)), 1e-15)
            result.mass_imbalance = abs(float(result.q_in) + float(result.q_out)) / denom

    def _apply_qc(self, result: COMSOLResult) -> None:
        if not result.convergence_evidence:
            result.run_status = "failed_solver"
            result.failure_class = "missing_convergence_evidence"
            if "missing_convergence_evidence" not in result.errors:
                result.errors.append("missing_convergence_evidence")
            return

        missing_outputs = [
            name
            for name, value in {
                "q_in": result.q_in,
                "q_out": result.q_out,
                "p_in": result.p_in,
                "p_out": result.p_out,
                "delta_p": result.delta_p,
            }.items()
            if not self._is_present(value)
        ]
        if missing_outputs:
            result.run_status = "failed_extraction"
            result.failure_class = "missing_required_outputs"
            result.errors.append(
                f"missing_required_outputs: {', '.join(sorted(missing_outputs))}"
            )
            return

        if bool(self.qc_thresholds.get("require_realized_geometry", True)) and not result.realized_geometry_present:
            result.run_status = "failed_extraction"
            result.failure_class = "missing_realized_geometry"
            if "missing_realized_geometry" not in result.errors:
                result.errors.append("missing_realized_geometry")
            return

        fail_reasons: List[str] = []
        thresholds = self.qc_thresholds

        if bool(thresholds.get("require_explicit_solver_tolerance", True)):
            if result.solver_relative_tolerance is None:
                fail_reasons.append("missing_solver_tolerance")
            elif result.solver_relative_tolerance > float(thresholds["max_solver_relative_tolerance"]):
                fail_reasons.append("solver_tolerance_too_loose")

        required_values = [result.q_in, result.q_out, result.p_in, result.p_out, result.delta_p]
        if bool(thresholds.get("require_finite_outputs", True)):
            if any(not self._is_finite(value) for value in required_values):
                fail_reasons.append("non_finite_outputs")

        if self.expected_delta_p_pa is not None and self._is_finite(result.delta_p):
            if abs(float(result.delta_p) - float(self.expected_delta_p_pa)) > float(
                thresholds.get("delta_p_abs_tolerance_pa", 1.0)
            ):
                fail_reasons.append("delta_p_mismatch")

        if bool(thresholds.get("require_pressure_sign_consistency", True)):
            if not (float(result.p_in) > float(result.p_out) and float(result.delta_p) > 0.0):
                fail_reasons.append("pressure_sign_inconsistent")

        if bool(thresholds.get("require_flow_sign_consistency", True)):
            if not (float(result.q_in) < 0.0 < float(result.q_out)):
                fail_reasons.append("flow_sign_inconsistent")

        if result.mass_imbalance is None:
            fail_reasons.append("mass_balance_missing")
        elif float(result.mass_imbalance) > float(thresholds["max_mass_balance_error"]):
            fail_reasons.append("mass_balance_exceeds_threshold")

        if result.mesh_min_quality is None:
            fail_reasons.append("mesh_quality_missing")
        elif float(result.mesh_min_quality) < float(thresholds["min_mesh_quality"]):
            fail_reasons.append("mesh_quality_below_threshold")

        result.qc_fail_reasons = fail_reasons
        result.qc_passed = not fail_reasons

        if result.qc_passed:
            result.run_status = "valid"
            result.failure_class = ""
            return

        result.run_status = "invalid_qc"
        result.failure_class = "invalid_qc"
