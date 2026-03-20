#!/usr/bin/env python3
"""Run one COMSOL smoke attempt and emit a verbose compatibility report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.comsol.expectations import expected_artifact_names
from src.comsol.runner import COMSOLRunner
from src.utils.config import ConfigLoader


def _build_report(
    runner: COMSOLRunner,
    design_id: str,
    cad_file: Path,
    output_dir: Path,
    record: dict,
) -> dict:
    run_dir = output_dir / design_id
    selected_attempt_dir = Path(record["selected_attempt_dir"]) if record.get("selected_attempt_dir") else run_dir / "attempt_0"
    expected_files = expected_artifact_names(design_id)
    artifact_report = {}
    for key, filename in expected_files.items():
        path = selected_attempt_dir / filename
        artifact_report[key] = {
            "path": str(path),
            "exists": path.exists(),
        }

    raw_metrics = record.get("raw_metrics", {})
    if not isinstance(raw_metrics, dict):
        raw_metrics = {}

    report = {
        "base_mph": str(runner.base_mph),
        "cad_file": str(cad_file),
        "design_id": design_id,
        "template_contract_report": runner.inspect_template_contract(),
        "parser_expectations": runner.result_parser.expectations_snapshot(),
        "attempt_report": {
            "run_dir": str(run_dir),
            "selected_attempt": record.get("selected_attempt", ""),
            "selected_attempt_dir": str(selected_attempt_dir),
            "expected_artifacts": artifact_report,
        },
        "parse_report": {
            "run_status": record.get("run_status"),
            "failure_class": record.get("failure_class"),
            "qc_passed": record.get("qc_passed"),
            "qc_fail_reasons": record.get("qc_fail_reasons"),
            "errors": record.get("errors"),
            "found_raw_metric_keys": sorted(raw_metrics.keys()),
            "parsed_results_file": record.get("parsed_results_file", ""),
            "parsed_log_file": record.get("parsed_log_file", ""),
            "parsed_realized_geometry_file": record.get("parsed_realized_geometry_file", ""),
        },
    }
    return report


def _print_report(report: dict) -> None:
    template = report["template_contract_report"]
    parse = report["parse_report"]
    attempt = report["attempt_report"]
    print("COMSOL smoke-run compatibility report")
    print(f"base_mph: {report['base_mph']}")
    print(f"cad_file: {report['cad_file']}")
    print(f"design_id: {report['design_id']}")
    print()
    print("Template contract")
    print(f"  valid: {template['valid']}")
    print(f"  sidecar: {template['template_contract_path']}")
    if template["error"]:
        print(f"  error: {template['error']}")
    print()
    print("Attempt")
    print(f"  selected_attempt: {attempt['selected_attempt']}")
    print(f"  selected_attempt_dir: {attempt['selected_attempt_dir']}")
    for key, info in attempt["expected_artifacts"].items():
        print(f"  artifact[{key}]: exists={info['exists']} path={info['path']}")
    print()
    print("Parse/QC")
    print(f"  run_status: {parse['run_status']}")
    print(f"  failure_class: {parse['failure_class']}")
    print(f"  qc_passed: {parse['qc_passed']}")
    print(f"  qc_fail_reasons: {parse['qc_fail_reasons']}")
    print(f"  errors: {parse['errors']}")
    print(f"  found_raw_metric_keys: {', '.join(parse['found_raw_metric_keys'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one COMSOL smoke attempt and emit a compatibility report")
    parser.add_argument("--base_mph", required=True, help="Path to the prepared COMSOL template MPH")
    parser.add_argument("--cad_file", required=True, help="Path to one STEP design")
    parser.add_argument("--design_id", default=None, help="Optional design ID override")
    parser.add_argument("--output_dir", required=True, help="Output directory for the smoke run")
    parser.add_argument("--comsol_exec", default="comsol", help="Path to COMSOL executable")
    args = parser.parse_args()

    design_id = args.design_id or Path(args.cad_file).stem
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigLoader()
    sim_contract = dict(config.get_simulation_contract())
    failure_policy = dict(sim_contract.get("failure_policy", {}))
    failure_policy["max_remesh_retries"] = 0
    sim_contract["failure_policy"] = failure_policy

    runner = COMSOLRunner(
        comsol_exec=args.comsol_exec,
        base_mph=Path(args.base_mph),
        output_dir=output_dir,
        simulation_contract=sim_contract,
    )

    record = runner.run_batch(
        design_id=design_id,
        parameters={},
        cad_file=Path(args.cad_file),
    )
    report = _build_report(
        runner=runner,
        design_id=design_id,
        cad_file=Path(args.cad_file),
        output_dir=output_dir,
        record=record,
    )

    report_path = output_dir / design_id / f"{design_id}_compatibility_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))

    _print_report(report)
    print()
    print(f"compatibility_report: {report_path}")


if __name__ == "__main__":
    main()
