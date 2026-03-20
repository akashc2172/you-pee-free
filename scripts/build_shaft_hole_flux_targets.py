#!/usr/bin/env python3
"""Build ordered shaft-hole flux extraction targets from a .holes.json sidecar."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.comsol.hole_flux import build_shaft_hole_flux_targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shaft-hole flux extraction targets")
    parser.add_argument("--holes_json", required=True, help="Path to design_XXXX.holes.json")
    parser.add_argument("--output_csv", default=None, help="Optional output CSV path")
    parser.add_argument("--output_json", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    holes_json = Path(args.holes_json).resolve()
    stem = holes_json.name
    if stem.endswith(".holes.json"):
        stem = stem[: -len(".holes.json")]
    output_csv = Path(args.output_csv).resolve() if args.output_csv else holes_json.with_name(
        f"{stem}.shaft_hole_flux_targets.csv"
    )
    output_json = Path(args.output_json).resolve() if args.output_json else holes_json.with_name(
        f"{stem}.shaft_hole_flux_targets.json"
    )

    df = build_shaft_hole_flux_targets(holes_json)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    output_json.write_text(df.to_json(orient="records", indent=2))

    print(f"targets_csv: {output_csv}")
    print(f"targets_json: {output_json}")
    print(f"shaft_hole_count: {len(df)}")


if __name__ == "__main__":
    main()
