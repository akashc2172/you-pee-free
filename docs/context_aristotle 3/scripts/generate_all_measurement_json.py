#!/usr/bin/env python3
"""Generate .meters.json sidecars for existing campaign designs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.cad.stent_generator import StentGenerator, StentParameters


_PARAM_COLUMNS = {
    "stent_french": float,
    "stent_length": float,
    "r_t": float,
    "r_sh": float,
    "r_end": float,
    "n_prox": int,
    "n_mid": int,
    "n_dist": int,
    "section_length_prox": float,
    "section_length_dist": float,
    "unroofed_length": float,
    "freeze_coil_geometry": bool,
}


def _row_to_params(row: pd.Series) -> StentParameters:
    kwargs = {}
    for col, dtype in _PARAM_COLUMNS.items():
        val = row.get(col)
        if val is None or pd.isna(val):
            continue
        if dtype is bool:
            kwargs[col] = bool(val)
        elif dtype is int:
            kwargs[col] = int(float(val))
        else:
            kwargs[col] = float(val)
    return StentParameters(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate .meters.json sidecars for a campaign")
    parser.add_argument("--campaign", required=True, help="Campaign directory")
    parser.add_argument("--batch-csv", default=None, help="Override batch CSV path")
    parser.add_argument("--design-id", default=None, help="Restrict to one design_id")
    parser.add_argument("--force", action="store_true", help="Overwrite existing .meters.json files")
    args = parser.parse_args()

    campaign_dir = Path(args.campaign).resolve()
    cad_dir = campaign_dir / "cad"
    batch_csv = Path(args.batch_csv) if args.batch_csv else campaign_dir / "batch_0000.csv"

    if not batch_csv.exists():
        raise FileNotFoundError(f"batch CSV not found: {batch_csv}")

    df = pd.read_csv(batch_csv)
    if args.design_id:
        df = df[df["design_id"].astype(str) == str(args.design_id)]
    if df.empty:
        raise ValueError("no matching design rows found")

    generated = 0
    skipped = 0

    for _, row in df.iterrows():
        design_id = str(row["design_id"])
        step_path = cad_dir / f"{design_id}.step"
        meters_path = cad_dir / f"{design_id}.meters.json"

        if not step_path.exists():
            skipped += 1
            continue
        if meters_path.exists() and not args.force:
            skipped += 1
            continue

        params = _row_to_params(row)
        gen = StentGenerator(params)
        gen.generate()
        gen.export_measurement_surface_metadata(meters_path, design_id=design_id)
        generated += 1

    print(f"Generated {generated} measurement sidecars; skipped {skipped}")


if __name__ == "__main__":
    main()
