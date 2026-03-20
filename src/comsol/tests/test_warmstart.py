"""Tests for the warm-start manifest selector."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from src.comsol.warmstart import build_jobs_manifest


def _write_anchor_bank(path: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "anchor_design_id": "design_0000",
                "template_id": "len140",
                "family_label": "baselineA",
                "topology_label": "shaft_prox_dense",
                "stent_length_mm": 140,
                "hole_count_total": 12,
                "hole_diameter_mm": 0.40,
                "unroof_fraction": 0.12,
                "prox_hole_count": 4,
                "mid_hole_count": 4,
                "dist_hole_count": 4,
                "checkpoint_075_ready": True,
                "checkpoint_090_ready": True,
                "checkpoint_095_ready": True,
                "checkpoint_075_path": "C:/anchors/design_0000/p075.mphbin",
                "checkpoint_090_path": "C:/anchors/design_0000/p090.mphbin",
                "checkpoint_095_path": "C:/anchors/design_0000/p095.mphbin",
                "solve_status": "solved",
            },
            {
                "anchor_design_id": "design_0002",
                "template_id": "len220",
                "family_label": "baselineA",
                "topology_label": "shaft_prox_dense",
                "stent_length_mm": 220,
                "hole_count_total": 18,
                "hole_diameter_mm": 0.45,
                "unroof_fraction": 0.20,
                "prox_hole_count": 6,
                "mid_hole_count": 6,
                "dist_hole_count": 6,
                "checkpoint_075_ready": True,
                "checkpoint_090_ready": True,
                "checkpoint_095_ready": False,
                "checkpoint_075_path": "C:/anchors/design_0002/p075.mphbin",
                "checkpoint_090_path": "C:/anchors/design_0002/p090.mphbin",
                "checkpoint_095_path": "",
                "solve_status": "solved",
            },
        ]
    )
    frame.to_csv(path, index=False)


def _write_metadata(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2))


def test_selector_respects_template_id(tmp_path: Path) -> None:
    anchor_bank = tmp_path / "anchor_bank.csv"
    _write_anchor_bank(anchor_bank)
    metadata = tmp_path / "design_0100.metadata.json"
    _write_metadata(
        metadata,
        {
            "design_id": "design_0100",
            "template_id": "len140",
            "family_label": "baselineA",
            "topology_label": "shaft_prox_dense",
            "stent_length_mm": 141.0,
            "hole_count_total": 12,
            "hole_diameter_mm": 0.40,
            "unroof_fraction": 0.12,
            "prox_hole_count": 4,
            "mid_hole_count": 4,
            "dist_hole_count": 4,
            "measurement_metadata_path": "C:/inputs/design_0100/design_0100.meters.json",
            "holes_path": "C:/inputs/design_0100/design_0100.holes.json",
            "step_path": "C:/inputs/design_0100/design_0100.step",
        },
    )

    manifest = build_jobs_manifest(
        anchor_bank_path=anchor_bank,
        metadata_files=[metadata],
    )

    row = manifest.iloc[0]
    assert row["anchor_design_id"] == "design_0000"
    assert row["anchor_template_id"] == "len140"
    assert row["schedule_type"] == "warm95"


def test_topology_mismatch_forces_cold(tmp_path: Path) -> None:
    anchor_bank = tmp_path / "anchor_bank.csv"
    _write_anchor_bank(anchor_bank)
    metadata = tmp_path / "design_0102.metadata.json"
    _write_metadata(
        metadata,
        {
            "design_id": "design_0102",
            "template_id": "len140",
            "family_label": "baselineA",
            "topology_label": "shaft_sparse_open",
            "stent_length_mm": 140.0,
            "hole_count_total": 12,
            "hole_diameter_mm": 0.40,
            "unroof_fraction": 0.12,
            "prox_hole_count": 4,
            "mid_hole_count": 4,
            "dist_hole_count": 4,
            "measurement_metadata_path": "C:/inputs/design_0102/design_0102.meters.json",
            "holes_path": "C:/inputs/design_0102/design_0102.holes.json",
            "step_path": "C:/inputs/design_0102/design_0102.step",
        },
    )

    manifest = build_jobs_manifest(
        anchor_bank_path=anchor_bank,
        metadata_files=[metadata],
    )

    row = manifest.iloc[0]
    assert row["schedule_type"] == "cold"
    assert row["start_checkpoint"] == "cold"
    assert row["topology_match"] == "false"


def test_missing_095_checkpoint_falls_back_to_090(tmp_path: Path) -> None:
    anchor_bank = tmp_path / "anchor_bank.csv"
    _write_anchor_bank(anchor_bank)
    metadata = tmp_path / "design_0103.metadata.json"
    _write_metadata(
        metadata,
        {
            "design_id": "design_0103",
            "template_id": "len220",
            "family_label": "baselineA",
            "topology_label": "shaft_prox_dense",
            "stent_length_mm": 221.0,
            "hole_count_total": 18,
            "hole_diameter_mm": 0.445,
            "unroof_fraction": 0.205,
            "prox_hole_count": 6,
            "mid_hole_count": 6,
            "dist_hole_count": 6,
            "measurement_metadata_path": "C:/inputs/design_0103/design_0103.meters.json",
            "holes_path": "C:/inputs/design_0103/design_0103.holes.json",
            "step_path": "C:/inputs/design_0103/design_0103.step",
        },
    )

    manifest = build_jobs_manifest(
        anchor_bank_path=anchor_bank,
        metadata_files=[metadata],
    )

    row = manifest.iloc[0]
    assert row["requested_start_checkpoint"] == "0.95"
    assert row["start_checkpoint"] == "0.90"
    assert row["schedule_type"] == "warm90"
    assert row["anchor_checkpoint_path"] == "C:/anchors/design_0002/p090.mphbin"
