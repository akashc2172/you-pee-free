from pathlib import Path

import pandas as pd
import pytest

from scripts.run_comsol_campaign import _merge_results
from scripts.run_optimization_campaign import (
    build_manifest_entry,
    filter_valid_training_rows,
    resolve_effective_training_features,
)
from src.cad.stent_generator import StentGenerator, StentParameters
from src.utils.config import ConfigLoader


def test_resolve_effective_training_features_fallback_and_override():
    cfg = ConfigLoader()
    feature_names = cfg.get_parameter_names()

    row = {key: cfg.design_vars[key].default for key in feature_names}
    df = pd.DataFrame([row])

    X0 = resolve_effective_training_features(df, feature_names)
    assert X0.loc[0, "n_prox"] == row["n_prox"]

    df["realized_n_prox"] = 1
    df["realized_n_mid"] = 2
    df["realized_n_dist"] = 3
    X1 = resolve_effective_training_features(df, feature_names)
    assert X1.loc[0, "n_prox"] == 1
    assert X1.loc[0, "n_mid"] == 2
    assert X1.loc[0, "n_dist"] == 3


def test_filter_valid_training_rows_only_keeps_valid():
    df = pd.DataFrame(
        [
            {"design_id": "a", "run_status": "valid"},
            {"design_id": "b", "run_status": "pending_simulation"},
            {"design_id": "c", "run_status": "invalid_qc"},
            {"design_id": "d", "run_status": "failed_solver"},
        ]
    )

    filtered = filter_valid_training_rows(df)

    assert list(filtered["design_id"]) == ["a"]


def test_filter_valid_training_rows_requires_status_column():
    with pytest.raises(ValueError, match="run_status"):
        filter_valid_training_rows(pd.DataFrame([{"design_id": "a"}]))


def test_manifest_entry_separates_precomsol_and_realized_geometry():
    params = StentParameters(n_prox=1, n_mid=2, n_dist=1, unroofed_length=10.0)
    StentGenerator(params).generate()

    entry = build_manifest_entry(
        design_id="design_0001",
        params_dict={"stent_french": params.stent_french},
        stent_params=params,
        out_path=Path("/tmp/design_0001.step"),
        stl_path=None,
        stl_qa_pass=None,
        stl_fail_reasons="",
        sim_contract={
            "sim_contract_version": "v1_deltaP490_steady_laminar",
            "domain_template": "triple_domain_dumbbell",
            "selection_strategy": "coordinate_bbox",
        },
        fixed_cad_cfg={"coil_hole_radius_mode": "match_body_hole_radius"},
    )

    assert entry["precomsol_n_mid"] == params.realized_n_mid
    assert entry["precomsol_total_hole_area"] == params.realized_total_hole_area
    assert entry["realized_n_mid"] is None
    assert entry["realized_total_hole_area"] is None
    assert entry["run_status"] == "pending_simulation"


def test_merge_results_preserves_new_columns_on_rerun():
    existing = pd.DataFrame(
        [
            {
                "design_id": "design_0001",
                "run_status": "invalid_qc",
                "legacy_col": "old",
            }
        ]
    )
    new_rows = pd.DataFrame(
        [
            {
                "design_id": "design_0001",
                "run_status": "valid",
                "failure_class": "",
                "parsed_results_file": "/tmp/attempt_1/design_0001_results.csv",
            }
        ]
    )

    merged = _merge_results(existing, new_rows)

    assert list(merged["design_id"]) == ["design_0001"]
    assert merged.loc[0, "run_status"] == "valid"
    assert merged.loc[0, "legacy_col"] == "old"
    assert merged.loc[0, "parsed_results_file"].endswith("design_0001_results.csv")
