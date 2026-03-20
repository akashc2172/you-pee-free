#!/usr/bin/env python3
"""Stage a campaign for batch COMSOL execution on a Windows machine.

Uses -methodinputnames/-methodinputvalues CLI flags (COMSOL Programming
Reference Manual p.158) to override method-call inputs per design at
runtime. This means ONE reusable template .mph — no per-design editing.

Generates:
  staging_dir/
    design_XXXX/                   (output dir per design)
      design_XXXX.holes.json       (sidecar next to output .mph)
      design_XXXX.meters.json      (measurement-surface sidecar next to output .mph)
    design_XXXX.step               (STEP geometry, flat)
    run_all.bat                    (Windows batch loop)
    manifest.csv                   (tracking file)

Usage:
    python3 scripts/stage_comsol_campaign.py \\
        --campaign data/campaigns/campaign_len220 \\
        --staging-dir /tmp/comsol_staging \\
        --win-staging "C:\\akashcomsoltest" \\
        --win-template "C:\\akashcomsoltest\\baseline_template.mph" \\
        --win-comsol "C:\\Program Files\\COMSOL\\COMSOL61\\Multiphysics\\bin\\win64\\comsolbatch.exe"
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def _write_run_all_bat(
    path: Path,
    design_ids: list,
    win_staging: str,
    win_template: str,
    win_comsol: str,
) -> None:
    """Generate a Windows batch script using -methodinputnames/-methodinputvalues.

    Each comsolbatch invocation overrides the method-call inputs externally,
    so the template .mph never needs per-design editing.
    """
    # Forward slashes for COMSOL path arguments (works on Windows in COMSOL)
    win_staging_fwd = win_staging.replace("\\", "/")

    lines = [
        "@echo off",
        f'set COMSOL="{win_comsol}"',
        f'set TEMPLATE="{win_template}"',
        f'set STAGING="{win_staging}"',
        "",
        "echo ========================================",
        f"echo COMSOL batch run: {len(design_ids)} designs",
        "echo ========================================",
        "echo.",
        "",
    ]

    for design_id in design_ids:
        # Paths use forward slashes for the -methodinputvalues
        holes_path_fwd = f"{win_staging_fwd}/{design_id}/{design_id}.holes.json"
        cad_path_fwd = f"{win_staging_fwd}/{design_id}.step"

        lines.extend([
            f"echo === {design_id} ===",
            f"if exist %STAGING%\\{design_id}\\{design_id}_shaft_hole_flux.csv (",
            f"    echo SKIP {design_id}: results already exist",
            f"    echo {design_id} SKIPPED >> %STAGING%\\progress.txt",
            ") else (",
            f"    if not exist %STAGING%\\{design_id} mkdir %STAGING%\\{design_id}",
            # The key line: -methodinputnames/-methodinputvalues override
            # the method-call inputs at runtime without editing the .mph.
            f"    %COMSOL% -inputfile %TEMPLATE%"
            f" -outputfile %STAGING%\\{design_id}\\{design_id}.mph"
            f" -batchlog %STAGING%\\{design_id}\\{design_id}.log"
            f" -methodinputnames hole_metadata_path,design_id"
            f" -methodinputvalues {holes_path_fwd},{design_id}",
            f"    if errorlevel 1 (",
            f"        echo FAILED: {design_id} >> %STAGING%\\failures.txt",
            f"        echo {design_id} FAILED >> %STAGING%\\progress.txt",
            f"    ) else (",
            f"        echo {design_id} DONE >> %STAGING%\\progress.txt",
            f"    )",
            ")",
            "echo.",
            "",
        ])

    lines.extend([
        "echo ========================================",
        "echo Batch complete. See progress.txt and failures.txt",
        "echo ========================================",
        "pause",
    ])

    path.write_text("\r\n".join(lines) + "\r\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage a campaign for batch COMSOL execution"
    )
    parser.add_argument("--campaign", required=True, help="Campaign directory")
    parser.add_argument("--staging-dir", required=True, help="Local staging directory to create")
    parser.add_argument(
        "--win-staging",
        default="C:\\akashcomsoltest",
        help="Windows-side staging path (no spaces!)",
    )
    parser.add_argument(
        "--win-template",
        default="C:\\akashcomsoltest\\baseline_template.mph",
        help="Windows-side path to the baseline .mph template",
    )
    parser.add_argument(
        "--win-comsol",
        default="C:\\Program Files\\COMSOL\\COMSOL61\\Multiphysics\\bin\\win64\\comsolbatch.exe",
        help="Windows-side path to comsolbatch.exe",
    )
    parser.add_argument(
        "--max-designs",
        type=int,
        default=None,
        help="Limit to first N designs (for testing)",
    )
    args = parser.parse_args()

    campaign_dir = Path(args.campaign).resolve()
    cad_dir = campaign_dir / "cad"
    staging_dir = Path(args.staging_dir).resolve()
    staging_dir.mkdir(parents=True, exist_ok=True)

    if not cad_dir.exists():
        print(f"ERROR: CAD directory not found: {cad_dir}")
        sys.exit(1)

    # Find all design triples (STEP + holes.json + meters.json)
    step_files = sorted(cad_dir.glob("design_*.step"))
    design_ids = []
    missing_sidecars = []

    for step_file in step_files:
        design_id = step_file.stem
        holes_file = cad_dir / f"{design_id}.holes.json"
        meters_file = cad_dir / f"{design_id}.meters.json"
        if not holes_file.exists() or not meters_file.exists():
            missing_sidecars.append(design_id)
            continue
        design_ids.append(design_id)

    if missing_sidecars:
        print(f"WARNING: {len(missing_sidecars)} designs missing .holes.json or .meters.json:")
        for did in missing_sidecars[:5]:
            print(f"  {did}")
        if len(missing_sidecars) > 5:
            print(f"  ... and {len(missing_sidecars) - 5} more")
        print("Run generate_all_holes_json.py first, or these designs will be skipped.")
        print()

    if args.max_designs:
        design_ids = design_ids[: args.max_designs]

    if not design_ids:
        print("ERROR: No complete design pairs found")
        sys.exit(1)

    print(f"Staging {len(design_ids)} designs to {staging_dir}")

    # Copy files: STEP flat, holes.json into per-design output dir
    manifest_rows = []
    for design_id in design_ids:
        step_src = cad_dir / f"{design_id}.step"
        holes_src = cad_dir / f"{design_id}.holes.json"
        meters_src = cad_dir / f"{design_id}.meters.json"

        # STEP stays flat (COMSOL reads it from the staging root)
        shutil.copy2(step_src, staging_dir / f"{design_id}.step")

        # .holes.json goes into the per-design output directory
        # (next to where output .mph will land)
        design_output_dir = staging_dir / design_id
        design_output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(holes_src, design_output_dir / f"{design_id}.holes.json")
        shutil.copy2(meters_src, design_output_dir / f"{design_id}.meters.json")

        manifest_rows.append({
            "design_id": design_id,
            "step_file": f"{design_id}.step",
            "holes_json": f"{design_id}/{design_id}.holes.json",
            "meters_json": f"{design_id}/{design_id}.meters.json",
            "status": "pending",
        })

    # Write manifest
    manifest_path = staging_dir / "manifest.csv"
    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_rows[0].keys())
        writer.writeheader()
        writer.writerows(manifest_rows)

    # Write run_all.bat
    bat_path = staging_dir / "run_all.bat"
    _write_run_all_bat(
        bat_path,
        design_ids,
        args.win_staging,
        args.win_template,
        args.win_comsol,
    )

    print(f"\nStaging complete:")
    print(f"  {len(design_ids)} designs staged")
    print(f"  manifest.csv: {manifest_path}")
    print(f"  run_all.bat: {bat_path}")
    print()
    print("Key: run_all.bat uses -methodinputnames/-methodinputvalues")
    print("     to inject design-specific values into the method call")
    print("     at runtime. No per-design .mph editing required.")
    print()
    print(f"Next steps:")
    print(f"  1. Copy {staging_dir} → {args.win_staging} on the Windows machine")
    print(f"  2. Copy baseline template .mph → {args.win_template}")
    print(f"  3. Open cmd.exe, run: {args.win_staging}\\run_all.bat")
    print(f"  4. After completion, copy results back to Mac")
    print(f"  5. Run scripts/collect_comsol_results.py to aggregate")


if __name__ == "__main__":
    main()
