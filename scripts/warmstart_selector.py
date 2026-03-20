#!/usr/bin/env python3
"""Emit a COMSOL jobs manifest from design metadata and a solved anchor bank."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.comsol.warmstart import write_jobs_manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select warm-start anchors and write jobs_manifest.csv"
    )
    parser.add_argument("--anchor-bank", required=True, help="Path to anchor_bank.csv")
    parser.add_argument("--metadata-dir", help="Directory containing *.metadata.json files")
    parser.add_argument(
        "--metadata-glob",
        default="*.metadata.json",
        help="Glob used inside --metadata-dir (default: *.metadata.json)",
    )
    parser.add_argument(
        "--metadata-file",
        action="append",
        default=[],
        help="Explicit metadata file. May be repeated.",
    )
    parser.add_argument(
        "--output-manifest",
        required=True,
        help="Destination jobs_manifest.csv",
    )
    parser.add_argument(
        "--initial-status",
        default="pending",
        help="Initial status column value (default: pending)",
    )
    return parser.parse_args()


def _collect_metadata_files(args: argparse.Namespace) -> list[Path]:
    files = [Path(path).resolve() for path in args.metadata_file]
    if args.metadata_dir:
        metadata_dir = Path(args.metadata_dir).resolve()
        files.extend(sorted(metadata_dir.glob(args.metadata_glob)))
    unique_files = sorted({path.resolve() for path in files})
    if not unique_files:
        raise SystemExit("No metadata files supplied. Use --metadata-dir or --metadata-file.")
    return unique_files


def main() -> None:
    args = _parse_args()
    metadata_files = _collect_metadata_files(args)
    manifest = write_jobs_manifest(
        anchor_bank_path=Path(args.anchor_bank).resolve(),
        metadata_files=metadata_files,
        output_manifest_path=Path(args.output_manifest).resolve(),
        initial_status=args.initial_status,
    )
    print(f"Wrote {len(manifest)} jobs to {Path(args.output_manifest).resolve()}")


if __name__ == "__main__":
    main()
