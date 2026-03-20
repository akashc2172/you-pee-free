#!/usr/bin/env python3
"""Generate .holes.json sidecars for all designs in a campaign.

Reads the campaign's batch CSV to reconstruct each StentGenerator with
the original LHS parameters, then calls export_hole_metadata() for
each design whose .holes.json does not yet exist.

Usage:
    python3 scripts/generate_all_holes_json.py \
        --campaign data/campaigns/campaign_len220
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.cad.stent_generator import StentGenerator, StentParameters


# StentParameters fields we read from the batch CSV.
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
    parser = argparse.ArgumentParser(
        description="Generate .holes.json sidecars for all designs in a campaign"
    )
    parser.add_argument("--campaign", required=True, help="Campaign directory")
    parser.add_argument("--batch-csv", default=None, help="Override batch CSV (default: batch_0000.csv in campaign dir)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if .holes.json already exists")
    args = parser.parse_args()

    campaign_dir = Path(args.campaign).resolve()
    cad_dir = campaign_dir / "cad"
    batch_csv = Path(args.batch_csv) if args.batch_csv else campaign_dir / "batch_0000.csv"

    if not batch_csv.exists():
        print(f"ERROR: batch CSV not found: {batch_csv}")
        sys.exit(1)

    df = pd.read_csv(batch_csv)
    if "design_id" not in df.columns:
        print("ERROR: batch CSV missing 'design_id' column")
        sys.exit(1)

    generated = 0
    skipped = 0
    failed = 0

    for _, row in df.iterrows():
        design_id = str(row["design_id"])
        step_path = cad_dir / f"{design_id}.step"
        holes_path = cad_dir / f"{design_id}.holes.json"

        if not step_path.exists():
            print(f"  SKIP {design_id}: STEP file not found")
            skipped += 1
            continue

        if holes_path.exists() and not args.force:
            print(f"  SKIP {design_id}: .holes.json already exists (use --force to overwrite)")
            skipped += 1
            continue

        try:
            params = _row_to_params(row)
            gen = StentGenerator(params)
            gen.generate()
            gen.export_hole_metadata(holes_path, design_id=design_id)
            generated += 1
            print(f"  OK   {design_id}")
        except Exception as exc:
            print(f"  FAIL {design_id}: {exc}")
            failed += 1

    print(f"\nDone: {generated} generated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
