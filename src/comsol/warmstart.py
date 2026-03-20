"""Mac-side warm-start selector for COMSOL batch manifests."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

SCHEDULES = {
    "cold": "0.1,0.5,0.75,0.9,0.95,0.9625,0.975,0.9875,0.995,1.0",
    "warm95": "0.95,0.9625,0.975,0.9875,0.995,1.0",
    "warm90": "0.90,0.95,0.9625,0.975,0.9875,0.995,1.0",
    "warm75": "0.75,0.9,0.95,0.9625,0.975,0.9875,0.995,1.0",
}

DEFAULT_SCALES = {
    "stent_length_mm": 120.0,
    "hole_count_total": 30.0,
    "hole_diameter_mm": 0.30,
    "unroof_fraction": 0.30,
    "prox_hole_count": 10.0,
    "mid_hole_count": 10.0,
    "dist_hole_count": 10.0,
}

DEFAULT_WEIGHTS = {
    "stent_length_mm": 1.0,
    "hole_count_total": 0.8,
    "hole_diameter_mm": 1.2,
    "unroof_fraction": 1.2,
    "prox_hole_count": 0.4,
    "mid_hole_count": 0.4,
    "dist_hole_count": 0.4,
}

FAMILY_MISMATCH_PENALTY = 0.0036
TOPOLOGY_MISMATCH_PENALTY = 0.25

REQUIRED_ANCHOR_COLUMNS = {
    "anchor_design_id",
    "template_id",
    "family_label",
    "topology_label",
    "stent_length_mm",
    "hole_count_total",
    "hole_diameter_mm",
    "unroof_fraction",
    "prox_hole_count",
    "mid_hole_count",
    "dist_hole_count",
    "checkpoint_075_ready",
    "checkpoint_090_ready",
    "checkpoint_095_ready",
    "checkpoint_075_path",
    "checkpoint_090_path",
    "checkpoint_095_path",
    "solve_status",
}

REQUIRED_METADATA_FIELDS = {
    "design_id",
    "template_id",
    "family_label",
    "topology_label",
    "stent_length_mm",
    "hole_count_total",
    "hole_diameter_mm",
    "unroof_fraction",
    "prox_hole_count",
    "mid_hole_count",
    "dist_hole_count",
    "measurement_metadata_path",
    "holes_path",
    "step_path",
}

CHECKPOINT_FALLBACKS = {
    "0.95": ["0.95", "0.90", "0.75"],
    "0.90": ["0.90", "0.75"],
    "0.75": ["0.75"],
}

CHECKPOINT_TO_SCHEDULE = {
    "0.95": "warm95",
    "0.90": "warm90",
    "0.75": "warm75",
}

CHECKPOINT_READY_COLUMN = {
    "0.95": "checkpoint_095_ready",
    "0.90": "checkpoint_090_ready",
    "0.75": "checkpoint_075_ready",
}

CHECKPOINT_PATH_COLUMN = {
    "0.95": "checkpoint_095_path",
    "0.90": "checkpoint_090_path",
    "0.75": "checkpoint_075_path",
}


@dataclass(frozen=True)
class DesignMetadata:
    design_id: str
    template_id: str
    family_label: str
    topology_label: str
    stent_length_mm: float
    hole_count_total: int
    hole_diameter_mm: float
    unroof_fraction: float
    prox_hole_count: int
    mid_hole_count: int
    dist_hole_count: int
    measurement_metadata_path: str
    holes_path: str
    step_path: str
    source_metadata_file: str

    @classmethod
    def from_json(cls, path: Path) -> "DesignMetadata":
        payload = json.loads(path.read_text())
        missing = sorted(REQUIRED_METADATA_FIELDS - set(payload.keys()))
        if missing:
            raise ValueError(f"design_metadata_missing_fields:{path}:{','.join(missing)}")
        return cls(
            design_id=str(payload["design_id"]).strip(),
            template_id=str(payload["template_id"]).strip(),
            family_label=str(payload["family_label"]).strip(),
            topology_label=str(payload["topology_label"]).strip(),
            stent_length_mm=float(payload["stent_length_mm"]),
            hole_count_total=int(payload["hole_count_total"]),
            hole_diameter_mm=float(payload["hole_diameter_mm"]),
            unroof_fraction=float(payload["unroof_fraction"]),
            prox_hole_count=int(payload["prox_hole_count"]),
            mid_hole_count=int(payload["mid_hole_count"]),
            dist_hole_count=int(payload["dist_hole_count"]),
            measurement_metadata_path=str(payload["measurement_metadata_path"]).strip(),
            holes_path=str(payload["holes_path"]).strip(),
            step_path=str(payload["step_path"]).strip(),
            source_metadata_file=str(path),
        )


def load_anchor_bank(anchor_bank_path: Path) -> pd.DataFrame:
    anchors = pd.read_csv(anchor_bank_path)
    missing = sorted(REQUIRED_ANCHOR_COLUMNS - set(anchors.columns))
    if missing:
        raise ValueError(
            f"anchor_bank_missing_columns:{anchor_bank_path}:{','.join(missing)}"
        )
    anchors = anchors.copy()
    anchors = anchors.loc[
        anchors["solve_status"].astype(str).str.strip().str.lower() == "solved"
    ].reset_index(drop=True)
    if anchors.empty:
        raise ValueError(f"anchor_bank_has_no_solved_rows:{anchor_bank_path}")
    return anchors


def _normalized_sqdiff(value: float, anchor_value: float, *, scale: float, weight: float) -> float:
    return weight * (((value - anchor_value) / scale) ** 2)


def compute_distance(design: DesignMetadata, anchor_row: pd.Series) -> Dict[str, Any]:
    numeric_sq = 0.0
    for key, scale in DEFAULT_SCALES.items():
        weight = DEFAULT_WEIGHTS[key]
        numeric_sq += _normalized_sqdiff(
            float(getattr(design, key)),
            float(anchor_row[key]),
            scale=scale,
            weight=weight,
        )

    family_match = design.family_label == str(anchor_row["family_label"]).strip()
    topology_match = design.topology_label == str(anchor_row["topology_label"]).strip()

    penalty_sq = 0.0
    if not family_match:
        penalty_sq += FAMILY_MISMATCH_PENALTY
    if not topology_match:
        penalty_sq += TOPOLOGY_MISMATCH_PENALTY

    distance = math.sqrt(numeric_sq + penalty_sq)
    return {
        "similarity_distance": distance,
        "numeric_distance_sq": numeric_sq,
        "family_match": family_match,
        "topology_match": topology_match,
    }


def select_anchor(anchors: pd.DataFrame, design: DesignMetadata) -> Dict[str, Any]:
    eligible = anchors.loc[anchors["template_id"].astype(str).str.strip() == design.template_id]
    if eligible.empty:
        raise ValueError(f"no_anchor_for_template_id:{design.template_id}")

    best: Dict[str, Any] | None = None
    for _, row in eligible.iterrows():
        distance_info = compute_distance(design, row)
        candidate = {**row.to_dict(), **distance_info}
        if best is None:
            best = candidate
            continue
        if candidate["similarity_distance"] < best["similarity_distance"]:
            best = candidate
            continue
        if math.isclose(
            candidate["similarity_distance"],
            best["similarity_distance"],
            rel_tol=0.0,
            abs_tol=1e-12,
        ) and str(candidate["anchor_design_id"]) < str(best["anchor_design_id"]):
            best = candidate
    if best is None:
        raise ValueError("select_anchor_called_with_no_candidates")
    return best


def _requested_checkpoint(distance: float, topology_match: bool) -> tuple[str, str, str]:
    if not topology_match:
        return "cold", "cold", "topology_mismatch_forces_cold"
    if distance <= 0.10:
        return "0.95", "warm95", "distance_le_0.10"
    if distance <= 0.20:
        return "0.90", "warm90", "distance_le_0.20"
    if distance <= 0.35:
        return "0.75", "warm75", "distance_le_0.35"
    return "cold", "cold", "distance_gt_0.35"


def _resolve_checkpoint(anchor: Dict[str, Any], requested_start: str) -> tuple[str, str, str, str]:
    if requested_start == "cold":
        return "cold", "cold", "", "cold_schedule_selected"

    for checkpoint in CHECKPOINT_FALLBACKS[requested_start]:
        if bool(anchor[CHECKPOINT_READY_COLUMN[checkpoint]]):
            schedule = CHECKPOINT_TO_SCHEDULE[checkpoint]
            checkpoint_path = str(anchor[CHECKPOINT_PATH_COLUMN[checkpoint]]).strip()
            if checkpoint == requested_start:
                note = f"use_{schedule}"
            else:
                note = f"fallback_from_{requested_start}_to_{checkpoint}"
            return checkpoint, schedule, checkpoint_path, note

    return "cold", "cold", "", f"anchor_missing_all_requested_checkpoints_from_{requested_start}"


def build_manifest_row(
    design: DesignMetadata,
    anchor_selection: Dict[str, Any],
    *,
    run_order: int,
    initial_status: str = "pending",
) -> Dict[str, Any]:
    requested_start, requested_schedule, requested_reason = _requested_checkpoint(
        float(anchor_selection["similarity_distance"]),
        bool(anchor_selection["topology_match"]),
    )
    start_checkpoint, schedule_type, anchor_checkpoint_path, resolution_note = _resolve_checkpoint(
        anchor_selection,
        requested_start,
    )
    selection_notes = requested_reason
    if resolution_note != "cold_schedule_selected":
        selection_notes = f"{selection_notes};{resolution_note}"

    return {
        "run_order": run_order,
        "design_id": design.design_id,
        "template_id": design.template_id,
        "family_label": design.family_label,
        "topology_label": design.topology_label,
        "source_metadata_file": design.source_metadata_file,
        "measurement_metadata_path": design.measurement_metadata_path,
        "holes_path": design.holes_path,
        "step_path": design.step_path,
        "anchor_design_id": anchor_selection["anchor_design_id"],
        "anchor_template_id": anchor_selection["template_id"],
        "anchor_family_label": anchor_selection["family_label"],
        "anchor_topology_label": anchor_selection["topology_label"],
        "similarity_distance": round(float(anchor_selection["similarity_distance"]), 6),
        "topology_match": str(bool(anchor_selection["topology_match"])).lower(),
        "family_match": str(bool(anchor_selection["family_match"])).lower(),
        "requested_start_checkpoint": requested_start,
        "requested_schedule_type": requested_schedule,
        "start_checkpoint": start_checkpoint,
        "schedule_type": schedule_type,
        "p_schedule": SCHEDULES[schedule_type],
        "anchor_checkpoint_path": anchor_checkpoint_path,
        "status": initial_status,
        "selection_notes": selection_notes,
    }


def build_jobs_manifest(
    *,
    anchor_bank_path: Path,
    metadata_files: Iterable[Path],
    initial_status: str = "pending",
) -> pd.DataFrame:
    anchors = load_anchor_bank(anchor_bank_path)
    rows: List[Dict[str, Any]] = []
    ordered_files = sorted(Path(path) for path in metadata_files)
    for index, metadata_file in enumerate(ordered_files, start=1):
        design = DesignMetadata.from_json(metadata_file)
        anchor_selection = select_anchor(anchors, design)
        rows.append(
            build_manifest_row(
                design,
                anchor_selection,
                run_order=index,
                initial_status=initial_status,
            )
        )
    if not rows:
        raise ValueError("no_design_metadata_files_found")
    return pd.DataFrame(rows)


def write_jobs_manifest(
    *,
    anchor_bank_path: Path,
    metadata_files: Iterable[Path],
    output_manifest_path: Path,
    initial_status: str = "pending",
) -> pd.DataFrame:
    manifest = build_jobs_manifest(
        anchor_bank_path=anchor_bank_path,
        metadata_files=metadata_files,
        initial_status=initial_status,
    )
    output_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(output_manifest_path, index=False)
    return manifest
