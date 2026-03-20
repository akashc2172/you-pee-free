#!/usr/bin/env python3
"""Run COMSOL for a campaign batch with checkpoint/resume and QC-gated outputs."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.comsol.runner import COMSOLRunner
from src.utils.config import ConfigLoader
from src.utils.logging_utils import setup_simple_logging


def _latest_batch_file(base_dir: Path) -> Path:
    candidates = sorted(base_dir.glob("batch_*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No batch_*.csv files found in {base_dir}")
    return candidates[-1]


def _merge_results(existing: pd.DataFrame, new_rows: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new_rows
    if "design_id" not in existing.columns or "design_id" not in new_rows.columns:
        return pd.concat([existing, new_rows], ignore_index=True)

    all_columns = sorted(set(existing.columns) | set(new_rows.columns))
    existing_aligned = existing.reindex(columns=all_columns).set_index("design_id", drop=False)
    incoming_aligned = new_rows.reindex(columns=all_columns).set_index("design_id", drop=False)
    merged = incoming_aligned.combine_first(existing_aligned)
    return merged.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run COMSOL batch for campaign")
    parser.add_argument("--campaign", required=True, help="Campaign folder under data/campaigns")
    parser.add_argument("--batch_file", default=None, help="Path to batch CSV (default: latest batch_*.csv)")
    parser.add_argument("--base_mph", required=True, help="Canonical COMSOL template MPH")
    parser.add_argument("--comsol_exec", default="comsol", help="Path to COMSOL executable")
    parser.add_argument("--output_dir", default=None, help="Override output dir for run folders")
    parser.add_argument("--results_file", default=None, help="Override aggregate results CSV path")
    parser.add_argument("--no_resume", action="store_true", help="Disable checkpoint resume behavior")

    args = parser.parse_args()

    setup_simple_logging()
    logger = logging.getLogger("COMSOLCampaign")

    config = ConfigLoader()
    sim_contract = config.get_simulation_contract()

    campaign_dir = project_root / "data" / "campaigns" / args.campaign
    campaign_dir.mkdir(parents=True, exist_ok=True)

    batch_file = Path(args.batch_file) if args.batch_file else _latest_batch_file(campaign_dir)
    if not batch_file.is_absolute():
        batch_file = (project_root / batch_file).resolve()
    if not batch_file.exists():
        raise FileNotFoundError(f"Batch file not found: {batch_file}")

    output_dir = Path(args.output_dir) if args.output_dir else campaign_dir / "comsol_runs"
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_path = output_dir / f"{batch_file.stem}_checkpoint.csv"
    batch_results_path = output_dir / f"{batch_file.stem}_results.csv"

    aggregate_results_path = (
        Path(args.results_file) if args.results_file else campaign_dir / "results.csv"
    )
    if not aggregate_results_path.is_absolute():
        aggregate_results_path = (project_root / aggregate_results_path).resolve()

    runner = COMSOLRunner(
        comsol_exec=args.comsol_exec,
        base_mph=Path(args.base_mph),
        output_dir=output_dir,
        simulation_contract=sim_contract,
    )

    logger.info("Running COMSOL campaign batch: %s", batch_file)
    logger.info("Simulation contract version: %s", sim_contract.get("sim_contract_version", "unversioned"))

    batch_df = runner.run_manifest(
        manifest=batch_file,
        checkpoint_path=checkpoint_path,
        resume=not args.no_resume,
    )
    batch_df.to_csv(batch_results_path, index=False)

    if aggregate_results_path.exists():
        existing = pd.read_csv(aggregate_results_path)
    else:
        existing = pd.DataFrame()

    merged = _merge_results(existing, batch_df)
    merged.to_csv(aggregate_results_path, index=False)

    status_counts = batch_df["run_status"].value_counts(dropna=False).to_dict()
    logger.info("Batch complete. Status counts: %s", status_counts)
    logger.info("Batch results: %s", batch_results_path)
    logger.info("Aggregate results: %s", aggregate_results_path)


if __name__ == "__main__":
    main()
