"""
COMSOL Runner.
Executes batch simulations with runtime-input hardening, template validation,
retry logic, and checkpointable manifests.
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from src.comsol.expectations import (
    ARTIFACT_FILENAME_TEMPLATES,
    PARSER_EXPECTATIONS_VERSION,
    REQUIRED_EXPORTS,
    REQUIRED_NAMED_SELECTIONS,
    REQUIRED_TEMPLATE_CONTRACT_FIELDS,
    TEMPLATE_CONTRACT_SCHEMA_VERSION,
)
from src.comsol.result_parser import COMSOLResult, ResultParser

TERMINAL_STATUSES = {
    "valid",
    "invalid_qc",
    "failed_solver",
    "failed_geometry",
    "failed_extraction",
}

COMSOL_RUNTIME_PARAMETER_ORDER = [
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

# Only explicit scalar boundary-condition overrides may come from a manifest row.
ALLOWED_MANIFEST_RUNTIME_OVERRIDES = {
    "p_inlet_pa",
    "p_outlet_pa",
    "delta_p_pa",
    "hole_metadata_path",
    "measurement_metadata_path",
}

class RuntimeParameterError(ValueError):
    """Raised when unsafe or undeclared COMSOL runtime parameters are supplied."""


class TemplateContractError(ValueError):
    """Raised when the external COMSOL template contract cannot be proven."""


class COMSOLRunner:
    """Executes COMSOL simulations."""

    def __init__(
        self,
        comsol_exec: str = "comsol",
        base_mph: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        simulation_contract: Optional[Dict[str, Any]] = None,
        result_parser: Optional[ResultParser] = None,
    ):
        self.comsol_exec = comsol_exec
        self.base_mph = Path(base_mph) if base_mph else None
        self.output_dir = Path(output_dir) if output_dir else Path("data/comsol_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("COMSOLRunner")

        self.simulation_contract = simulation_contract or {}
        self.failure_policy = self.simulation_contract.get("failure_policy", {})
        qc_thresholds = self.simulation_contract.get("qc_thresholds", {})
        boundary_conditions = self.simulation_contract.get("boundary_conditions", {})
        self.result_parser = result_parser or ResultParser(
            qc_thresholds=qc_thresholds,
            expected_delta_p_pa=boundary_conditions.get("delta_p_pa"),
        )

    def _base_model_exists(self) -> bool:
        return bool(self.base_mph and self.base_mph.exists())

    def _template_contract_path(self) -> Path:
        if not self.base_mph:
            raise FileNotFoundError("base_mph_not_configured")
        return self.base_mph.with_suffix(".contract.json")

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str))

    def _validate_template_contract(self) -> Dict[str, Any]:
        if not self._base_model_exists():
            raise FileNotFoundError(f"Base MPH file not found: {self.base_mph}")

        contract_path = self._template_contract_path()
        if not contract_path.exists():
            raise TemplateContractError(f"template_contract_missing: {contract_path}")

        try:
            contract = json.loads(contract_path.read_text())
        except json.JSONDecodeError as exc:
            raise TemplateContractError(f"template_contract_invalid_json: {exc}") from exc

        missing_fields = sorted(REQUIRED_TEMPLATE_CONTRACT_FIELDS - set(contract.keys()))
        if missing_fields:
            raise TemplateContractError(
                f"template_contract_missing_fields: {', '.join(missing_fields)}"
            )

        if str(contract["schema_version"]) != TEMPLATE_CONTRACT_SCHEMA_VERSION:
            raise TemplateContractError(
                f"template_contract_schema_version_mismatch: expected "
                f"{TEMPLATE_CONTRACT_SCHEMA_VERSION}, got {contract['schema_version']}"
            )

        if str(contract["parser_expectations_version"]) != PARSER_EXPECTATIONS_VERSION:
            raise TemplateContractError(
                f"template_parser_expectations_version_mismatch: expected "
                f"{PARSER_EXPECTATIONS_VERSION}, got {contract['parser_expectations_version']}"
            )

        expected_version = str(
            self.simulation_contract.get("sim_contract_version", contract["sim_contract_version"])
        )
        if str(contract["sim_contract_version"]) != expected_version:
            raise TemplateContractError(
                f"template_contract_version_mismatch: expected {expected_version}, "
                f"got {contract['sim_contract_version']}"
            )

        expected_domain_template = str(
            self.simulation_contract.get("domain_template", "triple_domain_dumbbell")
        )
        if str(contract["domain_template"]) != expected_domain_template:
            raise TemplateContractError(
                f"template_domain_template_mismatch: expected {expected_domain_template}, "
                f"got {contract['domain_template']}"
            )

        expected_selection_strategy = str(
            self.simulation_contract.get("selection_strategy", "coordinate_bbox")
        )
        if str(contract["selection_strategy"]) != expected_selection_strategy:
            raise TemplateContractError(
                f"template_selection_strategy_mismatch: expected {expected_selection_strategy}, "
                f"got {contract['selection_strategy']}"
            )

        named_selections = {str(item) for item in contract["required_named_selections"]}
        missing_named = sorted(REQUIRED_NAMED_SELECTIONS - named_selections)
        if missing_named:
            raise TemplateContractError(
                f"template_missing_named_selections: {', '.join(missing_named)}"
            )

        exports = {str(item) for item in contract["required_exports"]}
        missing_exports = sorted(REQUIRED_EXPORTS - exports)
        if missing_exports:
            raise TemplateContractError(
                f"template_missing_exports: {', '.join(missing_exports)}"
            )

        pressure_contract = contract["pressure_contract"]
        boundary_conditions = self.simulation_contract.get("boundary_conditions", {})
        expected_delta_p = boundary_conditions.get("delta_p_pa")
        if pressure_contract.get("mode") != boundary_conditions.get("mode", "pressure_driven"):
            raise TemplateContractError("template_pressure_mode_mismatch")
        if pressure_contract.get("delta_p_pa") != expected_delta_p:
            raise TemplateContractError(
                f"template_pressure_contract_mismatch: expected delta_p_pa={expected_delta_p}, "
                f"got {pressure_contract.get('delta_p_pa')}"
            )

        artifact_filenames = contract["artifact_filenames"]
        for key, template in ARTIFACT_FILENAME_TEMPLATES.items():
            if artifact_filenames.get(key) != template:
                raise TemplateContractError(
                    f"template_artifact_filename_mismatch: {key} expected {template}, "
                    f"got {artifact_filenames.get(key)}"
                )

        return contract

    def inspect_template_contract(self) -> Dict[str, Any]:
        report = {
            "base_mph": None if self.base_mph is None else str(self.base_mph),
            "template_contract_path": None,
            "valid": False,
            "error": "",
            "contract": None,
        }
        if self.base_mph is not None:
            report["template_contract_path"] = str(self._template_contract_path())
        try:
            contract = self._validate_template_contract()
        except (TemplateContractError, FileNotFoundError) as exc:
            report["error"] = str(exc)
            return report

        report["valid"] = True
        report["contract"] = contract
        return report

    @staticmethod
    def _extract_manifest_runtime_parameters(row: Dict[str, Any]) -> Dict[str, Any]:
        runtime = {
            key: value
            for key, value in row.items()
            if key in ALLOWED_MANIFEST_RUNTIME_OVERRIDES and pd.notna(value)
        }
        if "hole_metadata_file" in row and pd.notna(row["hole_metadata_file"]):
            runtime["hole_metadata_path"] = row["hole_metadata_file"]
        if "measurement_metadata_file" in row and pd.notna(row["measurement_metadata_file"]):
            runtime["measurement_metadata_path"] = row["measurement_metadata_file"]
        return runtime

    @staticmethod
    def _sanitize_runtime_scalar(name: str, value: Any) -> str:
        if isinstance(value, Path):
            value = str(value)
        if isinstance(value, bool):
            raise RuntimeParameterError(f"runtime_param_not_scalar: {name}")
        if isinstance(value, (list, tuple, dict, set)):
            raise RuntimeParameterError(f"runtime_param_not_scalar: {name}")
        if isinstance(value, (int, float)):
            if not math.isfinite(float(value)):
                raise RuntimeParameterError(f"runtime_param_not_finite: {name}")
            return str(value)
        if not isinstance(value, str):
            raise RuntimeParameterError(f"runtime_param_unsupported_type: {name}")

        text = value.strip()
        if not text:
            raise RuntimeParameterError(f"runtime_param_empty: {name}")
        if "," in text or "\n" in text or "\r" in text:
            raise RuntimeParameterError(f"runtime_param_unsafe_delimiter: {name}")
        if text.startswith("[") or text.startswith("{"):
            raise RuntimeParameterError(f"runtime_param_json_like: {name}")
        return text

    def _prepare_runtime_parameters(
        self,
        design_id: str,
        parameters: Dict[str, Any],
        cad_file: Path,
        attempt: int,
    ) -> Dict[str, str]:
        unexpected = sorted(set(parameters.keys()) - ALLOWED_MANIFEST_RUNTIME_OVERRIDES)
        if unexpected:
            raise RuntimeParameterError(
                f"undeclared_runtime_params: {', '.join(unexpected)}"
            )

        boundary_conditions = self.simulation_contract.get("boundary_conditions", {})
        runtime_values: Dict[str, Any] = {
            "cad_path": str(cad_file.resolve()),
            "hole_metadata_path": parameters.get(
                "hole_metadata_path",
                str(cad_file.with_suffix(".holes.json").resolve()),
            ),
            "measurement_metadata_path": parameters.get(
                "measurement_metadata_path",
                str(cad_file.with_suffix(".meters.json").resolve()),
            ),
            "design_id": design_id,
            "p_inlet_pa": parameters.get("p_inlet_pa", boundary_conditions.get("p_inlet_pa")),
            "p_outlet_pa": parameters.get("p_outlet_pa", boundary_conditions.get("p_outlet_pa")),
            "delta_p_pa": parameters.get("delta_p_pa", boundary_conditions.get("delta_p_pa")),
            "mesh_retry_level": attempt,
            "sim_contract_version": self.simulation_contract.get(
                "sim_contract_version", "unversioned"
            ),
            "domain_template": self.simulation_contract.get("domain_template", "unset"),
            "selection_strategy": self.simulation_contract.get("selection_strategy", "unset"),
        }

        missing = [name for name, value in runtime_values.items() if value is None]
        if missing:
            raise RuntimeParameterError(f"missing_runtime_params: {', '.join(sorted(missing))}")
        if not Path(str(runtime_values["hole_metadata_path"])).exists():
            raise RuntimeParameterError(
                f"hole_metadata_missing: {runtime_values['hole_metadata_path']}"
            )
        if not Path(str(runtime_values["measurement_metadata_path"])).exists():
            raise RuntimeParameterError(
                f"measurement_metadata_missing: {runtime_values['measurement_metadata_path']}"
            )

        sanitized: Dict[str, str] = {}
        for name in COMSOL_RUNTIME_PARAMETER_ORDER:
            sanitized[name] = self._sanitize_runtime_scalar(name, runtime_values[name])
        return sanitized

    def _build_command(
        self,
        output_mph: Path,
        log_file: Path,
        parameters: Dict[str, str],
    ) -> List[str]:
        pnames = [name for name in COMSOL_RUNTIME_PARAMETER_ORDER if name in parameters]
        pvals = [parameters[name] for name in pnames]
        return [
            self.comsol_exec,
            "batch",
            "-input",
            str(self.base_mph),
            "-output",
            str(output_mph),
            "-pname",
            ",".join(pnames),
            "-pval",
            ",".join(pvals),
            "-batchlog",
            str(log_file),
        ]

    def _failure_result(
        self,
        run_id: str,
        run_status: str,
        failure_class: str,
        error: str,
    ) -> COMSOLResult:
        result = COMSOLResult(run_id=run_id)
        result.run_status = run_status
        result.failure_class = failure_class
        result.errors.append(error)
        return result

    def run_batch(
        self,
        design_id: str,
        parameters: Dict[str, Any],
        cad_file: Path,
    ) -> Dict[str, Any]:
        """Run one simulation and return a flattened result/provenance record."""
        run_dir = self.output_dir / design_id
        run_dir.mkdir(parents=True, exist_ok=True)

        if not self._base_model_exists():
            result = self._failure_result(
                design_id,
                "failed_geometry",
                "failed_geometry",
                f"base_mph_missing: {self.base_mph}",
            )
            record = result.to_record()
            record["design_id"] = design_id
            record["run_dir"] = str(run_dir)
            self._write_json(run_dir / f"{design_id}_result.json", record)
            return record

        try:
            template_contract = self._validate_template_contract()
        except TemplateContractError as exc:
            result = self._failure_result(
                design_id,
                "failed_geometry",
                "failed_selection",
                str(exc),
            )
            record = result.to_record()
            record["design_id"] = design_id
            record["run_dir"] = str(run_dir)
            self._write_json(run_dir / f"{design_id}_result.json", record)
            return record
        except FileNotFoundError as exc:
            result = self._failure_result(
                design_id,
                "failed_geometry",
                "failed_geometry",
                str(exc),
            )
            record = result.to_record()
            record["design_id"] = design_id
            record["run_dir"] = str(run_dir)
            self._write_json(run_dir / f"{design_id}_result.json", record)
            return record

        if not Path(cad_file).exists():
            result = self._failure_result(
                design_id,
                "failed_geometry",
                "failed_geometry",
                f"cad_missing: {cad_file}",
            )
            record = result.to_record()
            record["design_id"] = design_id
            record["run_dir"] = str(run_dir)
            self._write_json(run_dir / f"{design_id}_result.json", record)
            return record

        provenance = {
            "design_id": design_id,
            "run_dir": str(run_dir),
            "cad_file": str(Path(cad_file).resolve()),
            "base_mph": str(self.base_mph.resolve()),
            "template_contract_path": str(self._template_contract_path().resolve()),
            "template_contract": template_contract,
            "simulation_contract": self.simulation_contract,
            "runtime_parameters": parameters,
        }
        self._write_json(run_dir / f"{design_id}_provenance.json", provenance)

        try:
            max_retries = int(self.failure_policy.get("max_remesh_retries", 1))
        except (TypeError, ValueError):
            max_retries = 1
        attempts = max_retries + 1
        final_result: Optional[COMSOLResult] = None
        selected_attempt: Optional[int] = None

        for attempt in range(attempts):
            attempt_dir = run_dir / f"attempt_{attempt}"
            attempt_dir.mkdir(parents=True, exist_ok=True)

            try:
                resolved_params = self._prepare_runtime_parameters(
                    design_id=design_id,
                    parameters=parameters,
                    cad_file=Path(cad_file),
                    attempt=attempt,
                )
            except RuntimeParameterError as exc:
                final_result = self._failure_result(
                    design_id,
                    "failed_geometry",
                    "invalid_runtime_parameters",
                    str(exc),
                )
                selected_attempt = attempt
                break

            output_mph = attempt_dir / f"{design_id}.mph"
            log_file = attempt_dir / f"{design_id}.log"
            cmd = self._build_command(output_mph, log_file, resolved_params)

            self.logger.info("Starting run %s (attempt %d/%d)", design_id, attempt + 1, attempts)
            self.logger.debug("Command: %s", " ".join(cmd))

            try:
                proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
                (attempt_dir / "stdout.log").write_text(proc.stdout or "")
                (attempt_dir / "stderr.log").write_text(proc.stderr or "")
            except subprocess.CalledProcessError as exc:
                (attempt_dir / "stdout.log").write_text(exc.stdout or "")
                (attempt_dir / "stderr.log").write_text(exc.stderr or "")
                final_result = self._failure_result(
                    design_id,
                    "failed_solver",
                    "failed_solver",
                    f"comsol_exit_{exc.returncode}",
                )
                selected_attempt = attempt
                if attempt + 1 < attempts:
                    continue
                break

            parsed = self.result_parser.parse_run(attempt_dir, design_id)
            final_result = parsed
            selected_attempt = attempt

            if parsed.run_status == "invalid_qc":
                retryable = any(
                    reason in {"mesh_quality_below_threshold", "mesh_quality_missing"}
                    for reason in parsed.qc_fail_reasons
                )
                if retryable and attempt + 1 < attempts:
                    self.logger.warning(
                        "Run %s failed QC (%s). Retrying with mesh_retry_level=%d",
                        design_id,
                        "; ".join(parsed.qc_fail_reasons),
                        attempt + 1,
                    )
                    continue
            break

        if final_result is None:
            final_result = self._failure_result(
                design_id,
                "failed_extraction",
                "failed_extraction",
                "missing_final_result",
            )

        record = final_result.to_record()
        record["design_id"] = design_id
        record["run_dir"] = str(run_dir)
        record["attempts_used"] = 0 if selected_attempt is None else selected_attempt + 1
        record["selected_attempt"] = (
            "" if selected_attempt is None else f"attempt_{selected_attempt}"
        )

        if selected_attempt is not None:
            selected_dir = run_dir / f"attempt_{selected_attempt}"
            record["selected_attempt_dir"] = str(selected_dir)
            record["parsed_results_file"] = str(selected_dir / f"{design_id}_results.csv")
            record["parsed_log_file"] = str(selected_dir / f"{design_id}.log")
            record["parsed_realized_geometry_file"] = str(
                selected_dir / f"{design_id}_realized_geometry.csv"
            )
        else:
            record["selected_attempt_dir"] = ""
            record["parsed_results_file"] = ""
            record["parsed_log_file"] = ""
            record["parsed_realized_geometry_file"] = ""

        record["qc_thresholds"] = json.dumps(self.result_parser.qc_thresholds)
        self._write_json(run_dir / f"{design_id}_result.json", record)
        return record

    def run_manifest(
        self,
        manifest: Union[Path, pd.DataFrame],
        checkpoint_path: Optional[Path] = None,
        resume: bool = True,
    ) -> pd.DataFrame:
        """Run an entire manifest with checkpoint/resume support."""
        if isinstance(manifest, pd.DataFrame):
            manifest_df = manifest.copy()
        else:
            manifest_df = pd.read_csv(manifest)

        if "design_id" not in manifest_df.columns:
            raise ValueError("manifest is missing required column: design_id")
        if "cad_file" not in manifest_df.columns:
            raise ValueError("manifest is missing required column: cad_file")

        checkpoint_path = checkpoint_path or (self.output_dir / "batch_checkpoint.csv")
        processed: Dict[str, Dict[str, Any]] = {}

        if resume and checkpoint_path.exists():
            cp = pd.read_csv(checkpoint_path)
            for _, row in cp.iterrows():
                status = str(row.get("run_status", ""))
                design_id = str(row.get("design_id", ""))
                if design_id and status in TERMINAL_STATUSES:
                    processed[design_id] = row.to_dict()

        records: List[Dict[str, Any]] = list(processed.values())

        for _, row in manifest_df.iterrows():
            design_id = str(row["design_id"])
            if design_id in processed:
                continue

            cad_file = Path(str(row["cad_file"]))
            parameters = self._extract_manifest_runtime_parameters(row.to_dict())

            try:
                result_record = self.run_batch(
                    design_id=design_id,
                    parameters=parameters,
                    cad_file=cad_file,
                )
            except Exception as exc:  # pragma: no cover - defensive
                result_record = {
                    "design_id": design_id,
                    "run_status": "failed_extraction",
                    "failure_class": "failed_extraction",
                    "errors": f"runner_exception: {exc}",
                }

            merged = row.to_dict()
            merged.update(result_record)
            records.append(merged)
            pd.DataFrame(records).to_csv(checkpoint_path, index=False)

        final_df = pd.DataFrame(records)
        final_df.to_csv(checkpoint_path, index=False)
        return final_df
