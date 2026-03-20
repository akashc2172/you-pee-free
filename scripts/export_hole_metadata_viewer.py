#!/usr/bin/env python3
"""Export a simple offline metadata viewer for a STEP + sidecar pair."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.visualization.hole_metadata_viewer import export_hole_metadata_viewer


def main() -> None:
    parser = argparse.ArgumentParser(description="Export 3D viewer for stent hole metadata")
    parser.add_argument("--step", required=True, help="Path to STEP geometry")
    parser.add_argument("--holes_json", required=True, help="Path to matching .holes.json metadata")
    parser.add_argument(
        "--meters_json",
        default=None,
        help="Optional matching .meters.json metadata (auto-detected if omitted)",
    )
    parser.add_argument("--output_dir", required=True, help="Directory for HTML + GLB viewer outputs")
    parser.add_argument("--shaft_only", action="store_true", help="Render shaft holes only")
    parser.add_argument("--coil_only", action="store_true", help="Render coil holes only")
    args = parser.parse_args()

    if args.shaft_only and args.coil_only:
        raise SystemExit("Choose at most one of --shaft_only or --coil_only")

    show_shaft = not args.coil_only
    show_coil = not args.shaft_only

    outputs = export_hole_metadata_viewer(
        step_path=Path(args.step),
        holes_json=Path(args.holes_json),
        meters_json=Path(args.meters_json) if args.meters_json else None,
        output_dir=Path(args.output_dir),
        show_shaft=show_shaft,
        show_coil=show_coil,
    )

    print(f"html={outputs['html']}")
    print(f"glb={outputs['glb']}")
    if "meters_json" in outputs:
        print(f"meters_json={outputs['meters_json']}")


if __name__ == "__main__":
    main()
