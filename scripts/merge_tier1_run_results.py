#!/usr/bin/env python3
"""Merge Tier-1 flux extraction fields into the main campaign results.csv.

This is a post-processing step to inject canonical Tier-1 raw fields (e.g., 
deltaP_Pa, Q_out_ml_min, exchange_number, hole_flux_centroid_norm, 
hole_flux_iqs_norm) derived from the per-feature flux extraction back into 
the main results.csv so it can be safely used for surrogate training.

Usage:
    python3 scripts/merge_tier1_run_results.py \
        --results data/campaigns/campaign_len220/results.csv \
        --flux-summary data/campaigns/campaign_len220/campaign_flux_summary.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd


TIER1_MERGE_COLUMNS = [
    "Q_in_ml_min",
    "Q_out_ml_min",
    "deltaP_Pa",
    "conductance_ml_min_per_Pa",
    "Q_lumen_out_ml_min",
    "Q_annulus_out_ml_min",
    "frac_lumen_out",
    "frac_annulus_out",
    "p_in_avg_Pa",
    "p_out_avg_Pa",
    "Q_holes_net_ml_min",
    "Q_holes_abs_ml_min",
    "hole_uniformity_cv",
    "hole_uniformity_gini",
    "n_active_holes",
    "prox_hole_abs_flux_ml_min",
    "mid_hole_abs_flux_ml_min",
    "dist_hole_abs_flux_ml_min",
    "frac_prox_hole_abs",
    "frac_mid_hole_abs",
    "frac_dist_hole_abs",
    "Q_unroof_net_ml_min",
    "Q_unroof_abs_ml_min",
    "frac_unroof_of_total",
    "frac_unroof_of_outlet_flow",
    "frac_unroof_of_exchange_total",
    "unroof_flux_density_ml_min_per_mm",
    "unroof_vs_holes_ratio",
    "Q_exchange_total_abs_ml_min",
    "exchange_number",
    "hole_only_exchange_number",
    "net_direction_index",
    "hole_flux_centroid_x_mm",
    "hole_flux_spread_x_mm",
    "hole_flux_dominance_ratio",
    "mass_balance_relerr",
    "invariants_passed",
    "invariant_warnings",
]


def _require_unique_design_ids(df: pd.DataFrame, *, frame_name: str) -> None:
    duplicated = df["design_id"].astype(str).duplicated(keep=False)
    if duplicated.any():
        dup_ids = sorted(df.loc[duplicated, "design_id"].astype(str).unique().tolist())
        raise ValueError(f"{frame_name} has duplicate design_id rows: {', '.join(dup_ids[:10])}")


def _select_flux_rows(flux_df: pd.DataFrame) -> pd.DataFrame:
    if "design_id" not in flux_df.columns:
        raise ValueError("flux summary is missing required column: design_id")

    working = flux_df.copy()
    working["design_id"] = working["design_id"].astype(str)
    working["_row_order"] = range(len(working))

    if "p_ramp" in working.columns:
        working["_p_ramp_numeric"] = pd.to_numeric(working["p_ramp"], errors="coerce")
        duplicate_keys = working[["design_id", "_p_ramp_numeric"]].duplicated(keep=False)
        exact_dupes = working.loc[duplicate_keys & working["_p_ramp_numeric"].notna(), "design_id"].unique()
        if len(exact_dupes) > 0:
            dup_ids = sorted(str(value) for value in exact_dupes)
            raise ValueError(
                "flux summary has duplicate design_id/p_ramp rows: " + ", ".join(dup_ids[:10])
            )
        working["_has_numeric_p_ramp"] = working["_p_ramp_numeric"].notna().astype(int)
        working = working.sort_values(
            by=["design_id", "_has_numeric_p_ramp", "_p_ramp_numeric", "_row_order"],
            ascending=[True, True, True, True],
            na_position="first",
        )
    else:
        working["_p_ramp_numeric"] = pd.NA
        working["_has_numeric_p_ramp"] = 0
        _require_unique_design_ids(working, frame_name="flux summary")

    selected = working.drop_duplicates(subset=["design_id"], keep="last").copy()
    return selected.drop(columns=["_row_order", "_p_ramp_numeric", "_has_numeric_p_ramp"])


def merge_tier1_results(results_df: pd.DataFrame, flux_df: pd.DataFrame) -> pd.DataFrame:
    if "design_id" not in results_df.columns:
        raise ValueError("results.csv is missing required column: design_id")

    working_results = results_df.copy()
    working_results["design_id"] = working_results["design_id"].astype(str)
    _require_unique_design_ids(working_results, frame_name="results.csv")

    selected_flux = _select_flux_rows(flux_df)
    available_cols = [col for col in TIER1_MERGE_COLUMNS if col in selected_flux.columns]
    if not available_cols:
        return working_results

    renamed_flux = selected_flux[["design_id", *available_cols]].rename(
        columns={col: f"__flux__{col}" for col in available_cols}
    )

    merged = working_results.merge(renamed_flux, on="design_id", how="left", validate="one_to_one")
    original_columns = set(working_results.columns)
    for col in available_cols:
        flux_col = f"__flux__{col}"
        if col in original_columns:
            merged[col] = merged[flux_col].where(merged[flux_col].notna(), merged[col])
            merged = merged.drop(columns=[flux_col])
        else:
            merged = merged.rename(columns={flux_col: col})
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Tier-1 flux metrics into results.csv")
    parser.add_argument(
        "--results",
        required=True,
        help="Path to the main results.csv (e.g. data/campaigns/my_campaign/results.csv)",
    )
    parser.add_argument(
        "--flux-summary",
        required=True,
        help="Path to the flux summary CSV (e.g. data/campaigns/my_campaign/campaign_flux_summary.csv)",
    )
    parser.add_argument(
        "--out",
        help="Output CSV path. If not provided, it will overwrite --results.",
    )
    args = parser.parse_args()

    results_path = Path(args.results).resolve()
    flux_path = Path(args.flux_summary).resolve()
    out_path = Path(args.out).resolve() if args.out else results_path

    if not results_path.exists():
        print(f"ERROR: results CSV not found at {results_path}")
        sys.exit(1)

    if not flux_path.exists():
        print(f"ERROR: flux summary CSV not found at {flux_path}")
        sys.exit(1)

    print(f"Loading results from: {results_path}")
    results_df = pd.read_csv(results_path)

    print(f"Loading flux summary from: {flux_path}")
    flux_df = pd.read_csv(flux_path)

    if "design_id" not in results_df.columns or "design_id" not in flux_df.columns:
        print("ERROR: Both CSVs must contain 'design_id' for merging.")
        sys.exit(1)

    try:
        selected_flux = _select_flux_rows(flux_df)
        merged = merge_tier1_results(results_df, flux_df)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    available_cols = [col for col in TIER1_MERGE_COLUMNS if col in selected_flux.columns]
    matched_designs = int(merged["design_id"].isin(selected_flux["design_id"]).sum())
    missing_designs = sorted(set(merged["design_id"]) - set(selected_flux["design_id"]))

    print(
        f"Merged {len(available_cols)} Tier-1 columns into {len(results_df)} result rows "
        f"({matched_designs} design_id matches)."
    )
    if missing_designs:
        print(
            f"WARNING: {len(missing_designs)} results rows had no matching flux summary row: "
            + ", ".join(missing_designs[:10])
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    print(f"Saved merged results to: {out_path}")


if __name__ == "__main__":
    main()
