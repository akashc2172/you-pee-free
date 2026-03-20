from __future__ import annotations

import pandas as pd
import pytest

from scripts.merge_tier1_run_results import merge_tier1_results


def test_merge_tier1_results_preserves_non_tier1_columns_and_existing_values():
    results_df = pd.DataFrame(
        [
            {
                "design_id": "design_0000",
                "run_status": "valid",
                "notes": "keep_me",
                "deltaP_Pa": 500.0,
                "Q_out_ml_min": 10.0,
            }
        ]
    )
    flux_df = pd.DataFrame(
        [
            {
                "design_id": "design_0000",
                "p_ramp": 1.0,
                "deltaP_Pa": 490.0,
                "Q_out_ml_min": pd.NA,
                "exchange_number": 0.25,
                "parsed_run_status": "valid",
            }
        ]
    )

    merged = merge_tier1_results(results_df, flux_df)
    row = merged.iloc[0]

    assert row["run_status"] == "valid"
    assert row["notes"] == "keep_me"
    assert row["deltaP_Pa"] == pytest.approx(490.0)
    assert row["Q_out_ml_min"] == pytest.approx(10.0)
    assert row["exchange_number"] == pytest.approx(0.25)
    assert "parsed_run_status" not in merged.columns


def test_merge_tier1_results_rejects_duplicate_flux_rows_for_same_design_and_pramp():
    results_df = pd.DataFrame([{"design_id": "design_0000", "run_status": "valid"}])
    flux_df = pd.DataFrame(
        [
            {"design_id": "design_0000", "p_ramp": 1.0, "deltaP_Pa": 490.0},
            {"design_id": "design_0000", "p_ramp": 1.0, "deltaP_Pa": 491.0},
        ]
    )

    with pytest.raises(ValueError, match="duplicate design_id/p_ramp"):
        merge_tier1_results(results_df, flux_df)


def test_merge_tier1_results_rejects_duplicate_results_design_ids():
    results_df = pd.DataFrame(
        [
            {"design_id": "design_0000", "run_status": "valid"},
            {"design_id": "design_0000", "run_status": "valid"},
        ]
    )
    flux_df = pd.DataFrame([{"design_id": "design_0000", "deltaP_Pa": 490.0}])

    with pytest.raises(ValueError, match="results.csv has duplicate design_id rows"):
        merge_tier1_results(results_df, flux_df)
