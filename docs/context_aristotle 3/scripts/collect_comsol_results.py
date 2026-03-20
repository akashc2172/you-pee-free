#!/usr/bin/env python3
"""Collect and aggregate COMSOL results from a batch run.

After copying results back from the Windows COMSOL machine, this script
scans the output directory, parses each design's results, and produces
a single campaign-level summary CSV.

Usage:
    python3 scripts/collect_comsol_results.py \
        --results-dir /path/to/comsol_results \
        --output data/campaigns/campaign_len220/campaign_results.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.comsol.result_parser import ResultParser


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect and aggregate COMSOL batch results"
    )
    parser.add_argument("--results-dir", required=True, help="Directory containing design_XXXX/ subdirs with COMSOL outputs")
    parser.add_argument("--output", required=True, help="Output CSV path for aggregated results")
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional manifest.csv to cross-reference (adds pending/missing status)",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    if not results_dir.exists():
        print(f"ERROR: results directory not found: {results_dir}")
        sys.exit(1)

    result_parser = ResultParser()
    records = []

    # Find all design subdirectories
    design_dirs = sorted(
        d for d in results_dir.iterdir()
        if d.is_dir() and d.name.startswith("design_")
    )

    if not design_dirs:
        print(f"No design_* directories found in {results_dir}")
        sys.exit(1)

    print(f"Found {len(design_dirs)} design directories")

    for design_dir in design_dirs:
        design_id = design_dir.name

        # Check if results CSV exists (the primary COMSOL output)
        results_csv = design_dir / f"{design_id}_results.csv"
        if not results_csv.exists():
            # Check for log to distinguish "ran but failed" from "never ran"
            log_file = design_dir / f"{design_id}.log"
            records.append({
                "design_id": design_id,
                "run_status": "never_ran" if not log_file.exists() else "failed_extraction",
                "failure_class": "missing_results_csv",
            })
            print(f"  MISS {design_id}")
            continue

        try:
            result = result_parser.parse_run(design_dir, design_id)
            record = result.to_record()
            record["design_id"] = design_id
            records.append(record)
            status = result.run_status
            print(f"  {'OK  ' if status == 'valid' else 'FAIL'} {design_id}: {status}")
        except Exception as exc:
            records.append({
                "design_id": design_id,
                "run_status": "parse_error",
                "failure_class": "parse_error",
                "errors": str(exc),
            })
            print(f"  ERR  {design_id}: {exc}")

    # Build summary DataFrame
    df = pd.DataFrame(records)

    # Cross-reference with manifest if provided
    if args.manifest and Path(args.manifest).exists():
        manifest_df = pd.read_csv(args.manifest)
        if "design_id" in manifest_df.columns:
            manifest_ids = set(manifest_df["design_id"].astype(str))
            found_ids = set(df["design_id"].astype(str))
            missing_ids = manifest_ids - found_ids
            if missing_ids:
                for mid in sorted(missing_ids):
                    df = pd.concat([df, pd.DataFrame([{
                        "design_id": mid,
                        "run_status": "not_found",
                        "failure_class": "not_in_results_dir",
                    }])], ignore_index=True)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    # Print summary
    status_counts = df["run_status"].value_counts()
    print(f"\n{'='*40}")
    print(f"Results summary: {len(df)} designs")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
