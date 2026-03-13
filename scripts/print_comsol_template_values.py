#!/usr/bin/env python3
"""Print deterministic COMSOL template values for one generated design."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import yaml

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cad.stent_generator import StentGenerator, StentParameters
from src.utils.config import ConfigLoader


def _load_reference_config(reference_path: Path) -> Dict[str, Any]:
    with reference_path.open("r") as handle:
        return yaml.safe_load(handle)


def _load_design_row(campaign_dir: Path, design_id: str) -> Dict[str, Any]:
    sources = []
    results_path = campaign_dir / "results.csv"
    if results_path.exists():
        sources.append(results_path)
    sources.extend(sorted(campaign_dir.glob("batch_*.csv"), reverse=True))

    for source in sources:
        df = pd.read_csv(source)
        if "design_id" not in df.columns:
            continue
        matches = df[df["design_id"] == design_id]
        if not matches.empty:
            return matches.iloc[-1].to_dict()

    raise FileNotFoundError(
        f"Could not find design_id={design_id} in {campaign_dir}/results.csv or batch_*.csv"
    )


def _build_params(row: Dict[str, Any], config: ConfigLoader) -> StentParameters:
    params_dict: Dict[str, Any] = {}
    for name in config.get_parameter_names():
        value = row.get(name)
        if pd.notna(value):
            params_dict[name] = value

    fixed_cad = config.get_fixed_cad_settings()
    if "freeze_coil_geometry" not in params_dict:
        params_dict["freeze_coil_geometry"] = bool(fixed_cad.get("freeze_coil_geometry", True))

    return StentParameters(**params_dict)


def _build_template_values(stent_params: StentParameters, reference_cfg: Dict[str, Any]) -> Dict[str, Any]:
    gen = StentGenerator(stent_params)
    gen.generate()
    p = gen.params

    dims = reference_cfg["dumbbell_dimensions_mm"]
    box_cfg = reference_cfg["selection_boxes_mm"]

    kidney_radius = float(dims["kidney_reservoir_radius_mm"])
    kidney_length = float(dims["kidney_reservoir_length_mm"])
    ureter_radius = float(dims["ureter_tube_radius_mm"])
    bladder_radius = float(dims["bladder_reservoir_radius_mm"])
    bladder_length = float(dims["bladder_reservoir_length_mm"])

    inlet_thickness = float(box_cfg["inlet_cap_thickness_mm"])
    outlet_thickness = float(box_cfg["outlet_cap_thickness_mm"])
    coil_half_width = float(box_cfg["coil_zone_yz_half_width_mm"])
    mid_half_width = float(box_cfg["mid_zone_yz_half_width_mm"])
    mid_start_fraction = float(box_cfg["mid_zone_start_fraction"])
    mid_end_fraction = float(box_cfg["mid_zone_end_fraction"])

    body_start_x = float(p.export_body_start_x)
    body_end_x = float(p.export_body_end_x)
    body_center_y = float(p.export_body_center_y)
    body_center_z = float(p.export_body_center_z)
    bbox_min_x = float(p.export_bbox_min_x)
    bbox_max_x = float(p.export_bbox_max_x)
    body_length = body_end_x - body_start_x

    kidney_x = body_start_x - kidney_length
    ureter_x = body_start_x
    bladder_x = body_end_x

    inlet_half = inlet_thickness / 2.0
    outlet_half = outlet_thickness / 2.0

    values = {
        "metadata": {
            "export_body_start_x": body_start_x,
            "export_body_end_x": body_end_x,
            "export_bbox_min_x": bbox_min_x,
            "export_bbox_max_x": bbox_max_x,
            "export_body_center_y": body_center_y,
            "export_body_center_z": body_center_z,
            "export_body_axis": [
                float(p.export_body_axis.X),
                float(p.export_body_axis.Y),
                float(p.export_body_axis.Z),
            ],
            "export_body_center_start": [
                float(p.export_body_center_start.X),
                float(p.export_body_center_start.Y),
                float(p.export_body_center_start.Z),
            ],
            "export_body_center_end": [
                float(p.export_body_center_end.X),
                float(p.export_body_center_end.Y),
                float(p.export_body_center_end.Z),
            ],
        },
        "cylinders": {
            "kidney": {
                "x": kidney_x,
                "y": body_center_y,
                "z": body_center_z,
                "radius_mm": kidney_radius,
                "height_mm": kidney_length,
            },
            "ureter": {
                "x": ureter_x,
                "y": body_center_y,
                "z": body_center_z,
                "radius_mm": ureter_radius,
                "height_mm": body_length,
            },
            "bladder": {
                "x": bladder_x,
                "y": body_center_y,
                "z": body_center_z,
                "radius_mm": bladder_radius,
                "height_mm": bladder_length,
            },
        },
        "selection_boxes": {
            "inlet": {
                "x_range_mm": [kidney_x - inlet_half, kidney_x + inlet_half],
                "y_range_mm": [body_center_y - kidney_radius, body_center_y + kidney_radius],
                "z_range_mm": [body_center_z - kidney_radius, body_center_z + kidney_radius],
            },
            "outlet": {
                "x_range_mm": [bladder_x + bladder_length - outlet_half, bladder_x + bladder_length + outlet_half],
                "y_range_mm": [body_center_y - bladder_radius, body_center_y + bladder_radius],
                "z_range_mm": [body_center_z - bladder_radius, body_center_z + bladder_radius],
            },
            "coil_zone": {
                "proximal_x_range_mm": [bbox_min_x, body_start_x],
                "distal_x_range_mm": [body_end_x, bbox_max_x],
                "y_range_mm": [body_center_y - coil_half_width, body_center_y + coil_half_width],
                "z_range_mm": [body_center_z - coil_half_width, body_center_z + coil_half_width],
            },
            "mid_zone": {
                "x_range_mm": [
                    body_start_x + mid_start_fraction * body_length,
                    body_start_x + mid_end_fraction * body_length,
                ],
                "y_range_mm": [body_center_y - mid_half_width, body_center_y + mid_half_width],
                "z_range_mm": [body_center_z - mid_half_width, body_center_z + mid_half_width],
            },
        },
    }
    return values


def _print_human(values: Dict[str, Any], design_id: str, cad_file: str) -> None:
    print(f"Design: {design_id}")
    if cad_file:
        print(f"CAD file: {cad_file}")
    print()
    print("Metadata")
    for key, value in values["metadata"].items():
        print(f"  {key}: {value}")
    print()
    print("Cylinders")
    for name, spec in values["cylinders"].items():
        print(f"  {name}: x={spec['x']}, y={spec['y']}, z={spec['z']}, radius={spec['radius_mm']}, height={spec['height_mm']}")
    print()
    print("Selection boxes")
    for name, spec in values["selection_boxes"].items():
        print(f"  {name}: {spec}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Print COMSOL template values for one design")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--campaign", help="Campaign folder name under data/campaigns")
    group.add_argument("--campaign_dir", help="Explicit campaign directory")
    parser.add_argument("--design_id", required=True, help="Design ID to inspect")
    parser.add_argument(
        "--reference_config",
        default=str(project_root / "config" / "comsol_dumbbell_reference.yaml"),
        help="Path to the dumbbell reference config",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only")
    args = parser.parse_args()

    campaign_dir = Path(args.campaign_dir) if args.campaign_dir else (project_root / "data" / "campaigns" / args.campaign)
    if not campaign_dir.is_absolute():
        campaign_dir = (project_root / campaign_dir).resolve()

    config = ConfigLoader()
    reference_path = Path(args.reference_config)
    if not reference_path.is_absolute():
        reference_path = (project_root / reference_path).resolve()
    reference_cfg = _load_reference_config(reference_path)
    row = _load_design_row(campaign_dir, args.design_id)
    params = _build_params(row, config)
    values = _build_template_values(params, reference_cfg)

    payload = {
        "design_id": args.design_id,
        "campaign_dir": str(campaign_dir),
        "cad_file": str(row.get("cad_file", "")),
        "template_values": values,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    _print_human(values, args.design_id, str(row.get("cad_file", "")))


if __name__ == "__main__":
    main()
