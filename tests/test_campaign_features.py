from pathlib import Path

import pandas as pd
import pytest

from scripts.run_comsol_campaign import _merge_results
from scripts.run_optimization_campaign import (
    build_manifest_entry,
    filter_valid_training_rows,
    filter_rows_by_fixed_params,
    get_active_parameter_names,
    parse_fixed_param_overrides,
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


def test_parse_fixed_param_overrides_and_active_feature_names():
    cfg = ConfigLoader()
    fixed = parse_fixed_param_overrides(["stent_length=140"], cfg)
    assert fixed == {"stent_length": 140.0}

    active = get_active_parameter_names(cfg, fixed)
    assert "stent_length" not in active
    assert len(active) == len(cfg.get_parameter_names()) - 1


def test_filter_rows_by_fixed_params_numeric_stratum():
    df = pd.DataFrame(
        [
            {"design_id": "a", "stent_length": 140.0, "run_status": "valid"},
            {"design_id": "b", "stent_length": 220.0, "run_status": "valid"},
        ]
    )
    filtered = filter_rows_by_fixed_params(df, {"stent_length": 140.0})
    assert list(filtered["design_id"]) == ["a"]


def test_manifest_entry_separates_precomsol_and_realized_geometry():
    params = StentParameters(n_prox=1, n_mid=2, n_dist=1, unroofed_length=10.0)
    StentGenerator(params).generate()

    entry = build_manifest_entry(
        design_id="design_0001",
        params_dict={"stent_french": params.stent_french},
        stent_params=params,
        out_path=Path("/tmp/design_0001.step"),
        holes_path=Path("/tmp/design_0001.holes.json"),
        hole_metadata={
            "schema_version": "hole_metadata_sidecar_v2",
            "holes": [{"hole_id": "shaft_prox_000"}],
            "frame_definition": {"units": "mm"},
        },
        meters_path=Path("/tmp/design_0001.meters.json"),
        measurement_metadata={
            "schema_version": "measurement_surface_sidecar_v1",
            "features": [{"feature_id": "cap_hole_shaft_prox_000"}],
            "units": "mm",
        },
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
    assert entry["hole_metadata_file"].endswith("design_0001.holes.json")
    assert entry["hole_metadata_schema_version"] == "hole_metadata_sidecar_v2"
    assert entry["hole_metadata_hole_count"] == 1
    assert entry["hole_metadata_units"] == "mm"
    assert entry["measurement_metadata_file"].endswith("design_0001.meters.json")
    assert entry["measurement_metadata_schema_version"] == "measurement_surface_sidecar_v1"
    assert entry["measurement_feature_count"] == 1
    assert entry["measurement_metadata_units"] == "mm"
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
