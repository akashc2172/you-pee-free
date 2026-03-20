#!/usr/bin/env python3
"""Collect metadata-driven COMSOL extraction CSVs into campaign-level outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.comsol.flux_extraction import (
    load_flux_features_csv,
    load_flux_scalars_csv,
    summarize_flux_outputs,
)
from src.comsol.result_parser import ResultParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect COMSOL extraction CSVs")
    parser.add_argument("--results-dir", required=True, help="Directory containing design_XXXX subdirectories")
    parser.add_argument("--summary-out", required=True, help="Output summary CSV")
    parser.add_argument("--features-out", required=True, help="Output long-form feature CSV")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    design_dirs = sorted(d for d in results_dir.iterdir() if d.is_dir() and d.name.startswith("design_"))
    if not design_dirs:
        raise FileNotFoundError(f"No design_* directories found in {results_dir}")

    result_parser = ResultParser()
    summary_frames = []
    feature_frames = []

    for design_dir in design_dirs:
        design_id = design_dir.name
        scalars_csv = design_dir / f"{design_id}_flux_scalars.csv"
        features_csv = design_dir / f"{design_id}_flux_features.csv"
        if not scalars_csv.exists() or not features_csv.exists():
            continue

        scalars_df = load_flux_scalars_csv(scalars_csv)
        features_df = load_flux_features_csv(features_csv)
        features_df = features_df.copy()
        features_df["design_id"] = design_id

        summary_df = summarize_flux_outputs(design_id, scalars_df, features_df)

        try:
            run_result = result_parser.parse_run(design_dir, design_id)
            summary_df["solver_converged_flag"] = int(run_result.converged)
            summary_df["solver_message"] = "; ".join(run_result.errors) if run_result.errors else ""
            summary_df["mesh_ndof"] = pd.NA
            summary_df["parsed_run_status"] = run_result.run_status
        except Exception:
            summary_df["parsed_run_status"] = "unparsed"

        summary_frames.append(summary_df)
        feature_frames.append(features_df)

    if not summary_frames or not feature_frames:
        raise FileNotFoundError(
            f"No *_flux_scalars.csv / *_flux_features.csv pairs found in {results_dir}"
        )

    summary_out = Path(args.summary_out)
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    features_out = Path(args.features_out)
    features_out.parent.mkdir(parents=True, exist_ok=True)

    pd.concat(summary_frames, ignore_index=True).to_csv(summary_out, index=False)
    pd.concat(feature_frames, ignore_index=True).to_csv(features_out, index=False)


if __name__ == "__main__":
    main()
