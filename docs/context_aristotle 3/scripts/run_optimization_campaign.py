#!/usr/bin/env python3
"""
Orchestration script for the Stent Optimization Campaign.
Manages the Active Learning Loop:
1. Load existing experiment data.
2. Train GP surrogate model.
3. Suggest new candidate designs via Bayesian Optimization.
4. Generate CAD geometry for candidates.
5. Prepare COMSOL batch scripts.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import sys
import logging
import json
from typing import Any, Dict

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import ConfigLoader
from src.utils.logging_utils import setup_simple_logging
from src.surrogate.training import GPTrainer
from src.optimization.optimizer import BayesianOptimizer
from src.cad.stent_generator import StentGenerator, StentParameters, StlExportOptions
from src.sampling.lhs_generator import LHSGenerator
from src.sampling.feasibility import FeasibilityFilter
from src.surrogate.dataset import assemble_training_data


def resolve_effective_training_features(df: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Use realized hole-count features when available, fallback to requested."""
    return BayesianOptimizer.resolve_effective_features(df, feature_names)


def parse_fixed_param_overrides(
    raw_overrides: list[str] | None,
    config: ConfigLoader,
) -> Dict[str, Any]:
    """Parse CLI overrides like ['stent_length=140'] into typed config values."""
    if not raw_overrides:
        return {}

    overrides: Dict[str, Any] = {}
    valid_names = set(config.get_parameter_names())

    for raw in raw_overrides:
        if "=" not in raw:
            raise ValueError(f"Invalid --fixed-param '{raw}'. Expected name=value.")
        name, raw_value = raw.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        if name not in valid_names:
            raise ValueError(f"Unknown fixed parameter '{name}'.")
        if name in overrides:
            raise ValueError(f"Duplicate fixed parameter '{name}'.")

        var_cfg = config.design_vars[name]
        if var_cfg.type == "discrete":
            value: Any = int(round(float(raw_value)))
        else:
            value = float(raw_value)

        min_val, max_val = var_cfg.range
        if value < min_val or value > max_val:
            raise ValueError(
                f"Fixed parameter '{name}'={value} is outside allowed range [{min_val}, {max_val}]."
            )
        overrides[name] = value

    return overrides


def get_active_parameter_names(config: ConfigLoader, fixed_params: Dict[str, Any]) -> list[str]:
    """Return sampled/optimized parameter names after removing campaign-fixed overrides."""
    return [name for name in config.get_parameter_names() if name not in fixed_params]


def filter_rows_by_fixed_params(df: pd.DataFrame, fixed_params: Dict[str, Any]) -> pd.DataFrame:
    """Restrict a result table to the requested fixed-parameter stratum."""
    if not fixed_params:
        return df

    filtered = df.copy()
    for name, value in fixed_params.items():
        if name not in filtered.columns:
            raise ValueError(f"results.csv is missing required fixed-parameter column: {name}")
        column = filtered[name]
        if pd.api.types.is_numeric_dtype(column):
            filtered = filtered[np.isclose(column.astype(float), float(value), atol=1e-9)]
        else:
            filtered = filtered[column.astype(str) == str(value)]
    return filtered.reset_index(drop=True)


def filter_valid_training_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Restrict surrogate training input to production-valid simulation rows."""
    if "run_status" not in df.columns:
        raise ValueError("results.csv is missing required column: run_status")
    return df[df["run_status"] == "valid"].copy().reset_index(drop=True)


def build_manifest_entry(
    design_id: str,
    params_dict: Dict[str, Any],
    stent_params: StentParameters,
    out_path: Path,
    holes_path: Path,
    hole_metadata: Dict[str, Any],
    stl_path: Path | None,
    stl_qa_pass: bool | None,
    stl_fail_reasons: str,
    sim_contract: Dict[str, Any],
    fixed_cad_cfg: Dict[str, Any],
    meters_path: Path | None = None,
    measurement_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build one manifest entry without treating CAD-side values as production realized geometry."""
    entry = params_dict.copy()
    entry["design_id"] = design_id
    entry["cad_file"] = str(out_path)
    entry["hole_metadata_file"] = str(holes_path)
    entry["hole_metadata_schema_version"] = hole_metadata.get("schema_version", "")
    entry["hole_metadata_hole_count"] = len(hole_metadata.get("holes", []))
    entry["hole_metadata_units"] = hole_metadata.get("frame_definition", {}).get("units", "")
    entry["measurement_metadata_file"] = str(meters_path) if meters_path else ""
    measurement_metadata = measurement_metadata or {}
    entry["measurement_metadata_schema_version"] = measurement_metadata.get("schema_version", "")
    entry["measurement_feature_count"] = len(measurement_metadata.get("features", []))
    entry["measurement_metadata_units"] = measurement_metadata.get("units", "")
    entry["stl_file"] = str(stl_path) if stl_path else ""
    entry["stl_qa_pass"] = stl_qa_pass
    entry["stl_fail_reasons"] = stl_fail_reasons
    entry["sim_contract_version"] = sim_contract.get("sim_contract_version", "unversioned")
    entry["domain_template"] = sim_contract.get("domain_template", "unset")
    entry["selection_strategy"] = sim_contract.get("selection_strategy", "unset")
    entry["manifest_version"] = "v1"
    entry["requested_n_prox"] = stent_params.requested_n_prox
    entry["requested_n_mid"] = stent_params.requested_n_mid
    entry["requested_n_dist"] = stent_params.requested_n_dist
    entry["requested_midsection_hole_count"] = stent_params.requested_midsection_hole_count
    entry["requested_body_holes"] = stent_params.requested_body_holes
    entry["requested_coil_hole_count"] = getattr(stent_params, "requested_coil_hole_count", 0)
    entry["requested_total_hole_count"] = getattr(
        stent_params,
        "requested_total_hole_count",
        stent_params.requested_body_holes,
    )
    entry["requested_hole_positions"] = json.dumps(
        [round(x, 6) for x in stent_params.requested_hole_positions]
    )

    # CAD-side postprocess metrics are useful for diagnostics, but they are not
    # production realized geometry until COMSOL exports them from the solved model.
    entry["precomsol_n_prox"] = stent_params.realized_n_prox
    entry["precomsol_n_mid"] = stent_params.realized_n_mid
    entry["precomsol_n_dist"] = stent_params.realized_n_dist
    entry["precomsol_midsection_hole_count"] = stent_params.realized_midsection_hole_count
    entry["precomsol_body_holes"] = stent_params.realized_body_holes
    entry["precomsol_coil_hole_count"] = getattr(stent_params, "realized_coil_hole_count", 0)
    entry["precomsol_total_hole_count"] = getattr(
        stent_params,
        "realized_total_hole_count",
        stent_params.realized_body_holes,
    )
    entry["precomsol_body_hole_total_area"] = getattr(
        stent_params,
        "realized_body_hole_total_area",
        0.0,
    )
    entry["precomsol_total_hole_area"] = getattr(
        stent_params,
        "realized_total_hole_area",
        0.0,
    )
    entry["precomsol_body_hole_min_spacing"] = getattr(
        stent_params,
        "realized_body_hole_min_spacing",
        None,
    )
    entry["precomsol_body_hole_mean_spacing"] = getattr(
        stent_params,
        "realized_body_hole_mean_spacing",
        None,
    )
    entry["precomsol_nearest_neighbor_spacing"] = getattr(
        stent_params,
        "realized_nearest_neighbor_spacing",
        None,
    )
    entry["precomsol_hole_positions"] = json.dumps(
        [round(x, 6) for x in stent_params.realized_hole_positions]
    )
    entry["precomsol_arc_positions"] = json.dumps(
        [round(x, 6) for x in getattr(stent_params, "realized_arc_positions", [])]
    )

    for key in [
        "realized_n_prox",
        "realized_n_mid",
        "realized_n_dist",
        "realized_midsection_hole_count",
        "realized_body_holes",
        "realized_coil_hole_count",
        "realized_total_hole_count",
        "realized_body_hole_total_area",
        "realized_total_hole_area",
        "realized_body_hole_min_spacing",
        "realized_body_hole_mean_spacing",
        "realized_nearest_neighbor_spacing",
        "realized_hole_positions",
        "realized_arc_positions",
    ]:
        entry[key] = None

    entry["suppressed_holes_due_to_unroofed"] = stent_params.suppressed_holes_due_to_unroofed
    entry["suppressed_holes_due_to_clearance"] = stent_params.suppressed_holes_due_to_clearance
    entry["freeze_coil_geometry"] = stent_params.freeze_coil_geometry
    entry["coil_hole_radius_mode"] = fixed_cad_cfg.get(
        "coil_hole_radius_mode",
        "match_body_hole_radius",
    )
    entry["run_status"] = "pending_simulation"
    entry["failure_class"] = ""
    return entry


def main():
    parser = argparse.ArgumentParser(description="Run Optimization Campaign")
    parser.add_argument('--campaign', type=str, default="campaign_001", help="Campaign name")
    parser.add_argument('--batch_size', type=int, default=5, help="Number of new candidates to suggest")
    parser.add_argument('--init_lhs', action='store_true', help="Initialize with LHS sampling if no data exists")
    parser.add_argument('--n_init', type=int, default=20, help="Number of initial LHS samples")
    parser.add_argument('--export_stl', action='store_true', help="Also export STL files per design")
    parser.add_argument(
        '--fixed-param',
        action='append',
        default=[],
        help="Campaign-level fixed parameter override, e.g. --fixed-param stent_length=140",
    )
    parser.add_argument(
        '--stl_quality',
        choices=['draft', 'standard', 'high'],
        default=None,
        help="STL tessellation profile",
    )
    parser.add_argument(
        '--stl_validate',
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable STL mesh QA checks",
    )
    
    args = parser.parse_args()
    
    # Setup
    setup_simple_logging()
    logger = logging.getLogger("Campaign")
    
    base_dir = project_root / "data" / "campaigns" / args.campaign
    results_path = base_dir / "results.csv"
    cad_dir = base_dir / "cad"
    base_dir.mkdir(parents=True, exist_ok=True)
    cad_dir.mkdir(parents=True, exist_ok=True)
    
    config = ConfigLoader()
    stl_cfg = config.get_stl_export_config()
    fixed_cad_cfg = config.get_fixed_cad_settings()
    sim_contract = config.get_simulation_contract()
    fixed_params = parse_fixed_param_overrides(args.fixed_param, config)
    active_feature_names = get_active_parameter_names(config, fixed_params)
    stl_default_profile = stl_cfg.get("default_profile", "standard")
    stl_ascii = bool(stl_cfg.get("ascii_format", False))
    default_validate = bool(stl_cfg.get("validate_mesh", True))

    stl_profile = args.stl_quality or stl_default_profile
    stl_validate = default_validate if args.stl_validate is None else args.stl_validate
    stl_profiles = stl_cfg.get("profiles", {})

    if args.export_stl:
        logger.info(
            "STL export enabled: profile=%s validate=%s ascii=%s",
            stl_profile,
            stl_validate,
            stl_ascii,
        )
    if fixed_params:
        logger.info("Campaign fixed-parameter overrides: %s", fixed_params)
        logger.info("Active sampled dimensions after overrides: %s", active_feature_names)
    
    # 1. Load Data
    existing_data = None
    if results_path.exists():
        logger.info(f"Loading existing results from {results_path}")
        existing_data = pd.read_csv(results_path)
    else:
        logger.info("No existing results found.")
        
    # 2. Initialize if needed
    candidates = None
    if existing_data is None or len(existing_data) == 0:
        if args.init_lhs:
            logger.info(f"Initializing campaign with {args.n_init} LHS samples...")
            gen = LHSGenerator(config=config, fixed_params=fixed_params)
            raw_samples = gen.generate(n_samples=args.n_init * 3) # Oversample
            filt = FeasibilityFilter()
            valid_samples, _ = filt.filter(raw_samples)
            
            if len(valid_samples) < args.n_init:
                logger.warning(f"Only found {len(valid_samples)} valid LHS samples")
                candidates = valid_samples
            else:
                candidates = valid_samples.iloc[:args.n_init]
                
            logger.info(f"Generated {len(candidates)} initial candidates.")
        else:
            logger.error("No data and --init_lhs not specified. Exiting.")
            sys.exit(1)
            
    else:
        # 3. Active Learning Step
        valid_data = filter_valid_training_rows(existing_data)
        valid_data = filter_rows_by_fixed_params(valid_data, fixed_params)
        if valid_data.empty:
            logger.error(
                "No rows with run_status == 'valid' remain after applying fixed-parameter overrides."
            )
            sys.exit(1)

        logger.info(
            "Training surrogate on %d valid data points (filtered from %d total rows)...",
            len(valid_data),
            len(existing_data),
        )
        
        # Prepare Data
        feature_names = active_feature_names
        # Assemble schema-driven training data (valid rows + Tier-1 transformed outputs only)
        # This errors loudly if required surrogate targets are missing.
        assembled = assemble_training_data(
            results_df=valid_data,
            feature_columns=feature_names,
            include_optional_outputs=False,
        )
        X = resolve_effective_training_features(assembled.used_rows, feature_names)
        y = assembled.y
        
        # Train
        trainer = GPTrainer(output_dir=base_dir / "models")
        model, metrics = trainer.train(X, y)
        logger.info(f"Model trained. RMSE: {metrics['train_rmse']:.4f}, R2: {metrics['train_r2']:.4f}")
        
        # Optimize
        logger.info(f"Optimizing acquisition function for {args.batch_size} candidates...")
        optimizer = BayesianOptimizer(model, config, fixed_params=fixed_params)
        candidates = optimizer.suggest(n_candidates=args.batch_size)
        logger.info(f"Suggested {len(candidates)} new candidates.")

    # 4. Generate CAD
    if candidates is not None and not candidates.empty:
        logger.info("Generating CAD files...")
        
        # Determine next batch ID
        # If we are initializing, it's batch 0. If data exists, check max batch? 
        # For simplicity, we just name files by design hash or timestamp. 
        # Let's use sequential IDs based on total count.
        
        start_id = 0
        if existing_data is not None:
            # Try to parse max id from 'design_id' column if it exists
            if 'design_id' in existing_data.columns:
                 # Extract numbers
                 # design_005 -> 5
                 ids = existing_data['design_id'].str.extract(r'(\d+)').astype(float)
                 start_id = int(ids.max().iloc[0]) + 1
        
        new_entries = []
        stl_success = 0
        stl_fail = 0
        n_rebalanced = 0
        
        for i, (idx, row) in enumerate(candidates.iterrows()):
            design_id = f"design_{start_id + i:04d}"
            
            # Convert row to dict for parameters
            params_dict = row.to_dict()
            
            try:
                # Instantiate parameters (validation happens here too)
                params_dict["freeze_coil_geometry"] = bool(
                    fixed_cad_cfg.get("freeze_coil_geometry", True)
                )
                if not bool(fixed_cad_cfg.get("half_open_distal_enabled", True)):
                    params_dict["unroofed_length"] = 0.0
                stent_params = StentParameters(**params_dict)
                generator = StentGenerator(stent_params)
                
                # Generate
                # We can skip full generation if we just want STEP, but StentGenerator.build() does it.
                # Assuming .export_step calls .build() internally if needed, or we call .build()
                # Looking at StentGenerator code... let's explicitly build if needed.
                # Actually export_step should handle it.
                
                out_path = cad_dir / f"{design_id}.step"
                generator.export_step(out_path)
                holes_path = out_path.with_suffix(".holes.json")
                meters_path = out_path.with_suffix(".meters.json")
                if not holes_path.exists():
                    raise FileNotFoundError(f"hole metadata sidecar missing: {holes_path}")
                if not meters_path.exists():
                    raise FileNotFoundError(f"measurement metadata sidecar missing: {meters_path}")
                hole_metadata = json.loads(holes_path.read_text())
                measurement_metadata = json.loads(meters_path.read_text())
                
                logger.info(f"  Generated {out_path.name}")

                stl_path = None
                stl_qa_pass = None
                stl_fail_reasons = ""
                if args.export_stl:
                    stl_path = cad_dir / f"{design_id}.stl"

                    if stl_profile in stl_profiles:
                        profile_cfg = stl_profiles[stl_profile]
                        stl_options = StlExportOptions(
                            tolerance=float(profile_cfg["tolerance"]),
                            angular_tolerance=float(profile_cfg["angular_tolerance"]),
                            ascii_format=stl_ascii,
                            validate_mesh=stl_validate,
                            quality_profile=stl_profile,
                        )
                    else:
                        stl_options = StlExportOptions.from_profile(
                            quality_profile=stl_profile,
                            ascii_format=stl_ascii,
                            validate_mesh=stl_validate,
                        )

                    stl_meta = generator.export_stl(stl_path, options=stl_options)
                    qa_meta = stl_meta.get("qa") or {}
                    stl_qa_pass = qa_meta.get("passed") if stl_validate else None
                    fail_reasons = qa_meta.get("fail_reasons") or []
                    stl_fail_reasons = "; ".join(fail_reasons)
                    stl_success += 1
                
                # Record metadata
                entry = build_manifest_entry(
                    design_id=design_id,
                    params_dict=params_dict,
                    stent_params=stent_params,
                    out_path=out_path,
                    holes_path=holes_path,
                    hole_metadata=hole_metadata,
                    meters_path=meters_path,
                    measurement_metadata=measurement_metadata,
                    stl_path=stl_path,
                    stl_qa_pass=stl_qa_pass,
                    stl_fail_reasons=stl_fail_reasons,
                    sim_contract=sim_contract,
                    fixed_cad_cfg=fixed_cad_cfg,
                )
                new_entries.append(entry)
                if stent_params.requested_body_holes != stent_params.realized_body_holes:
                    n_rebalanced += 1
                
            except Exception as e:
                logger.error(f"Failed to generate {design_id}: {e}")
                if args.export_stl:
                    stl_fail += 1
        
        # Save Batch Manifest
        if new_entries:
            batch_df = pd.DataFrame(new_entries)
            batch_file = base_dir / f"batch_{start_id:04d}.csv"
            batch_df.to_csv(batch_file, index=False)
            logger.info(f"Saved batch manifest to {batch_file}")
            if args.export_stl:
                logger.info("STL export summary: success=%d failed=%d", stl_success, stl_fail)
            logger.info("Hole rebalance summary: %d/%d designs adjusted", n_rebalanced, len(new_entries))
            
            print("\n" + "="*50)
            print(f"NEXT STEPS for Batch {start_id}:")
            print(f"1. Run COMSOL simulation for designs listed in: {batch_file}")
            print(f"2. Append results to: {results_path}")
            print("="*50)

if __name__ == "__main__":
    main()
