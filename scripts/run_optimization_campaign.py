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
import sys
import logging
import torch

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import ConfigLoader
from src.utils.logging_utils import setup_simple_logging
from src.surrogate.training import GPTrainer
from src.optimization.optimizer import BayesianOptimizer
from src.cad.stent_generator import StentGenerator, StentParameters
from src.sampling.lhs_generator import LHSGenerator
from src.sampling.feasibility import FeasibilityFilter

def main():
    parser = argparse.ArgumentParser(description="Run Optimization Campaign")
    parser.add_argument('--campaign', type=str, default="campaign_001", help="Campaign name")
    parser.add_argument('--batch_size', type=int, default=5, help="Number of new candidates to suggest")
    parser.add_argument('--init_lhs', action='store_true', help="Initialize with LHS sampling if no data exists")
    parser.add_argument('--n_init', type=int, default=20, help="Number of initial LHS samples")
    
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
            gen = LHSGenerator()
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
        logger.info(f"Training surrogate on {len(existing_data)} data points...")
        
        # Prepare Data
        feature_names = config.get_parameter_names()
        X = existing_data[feature_names]
        y_cols = ['Q_out', 'delta_P'] # Make sure these match CSV headers exactly!
        
        # Check correctness of columns
        missing_cols = [c for c in y_cols if c not in existing_data.columns]
        if missing_cols:
             # Try lowercase
             y_cols = ['q_out', 'delta_p']
             missing_cols = [c for c in y_cols if c not in existing_data.columns]
             if missing_cols:
                 logger.error(f"Missing output columns in results: {missing_cols}")
                 sys.exit(1)
        
        y = existing_data[y_cols]
        
        # Train
        trainer = GPTrainer(output_dir=base_dir / "models")
        model, metrics = trainer.train(X, y)
        logger.info(f"Model trained. RMSE: {metrics['train_rmse']:.4f}, R2: {metrics['train_r2']:.4f}")
        
        # Optimize
        logger.info(f"Optimizing acquisition function for {args.batch_size} candidates...")
        optimizer = BayesianOptimizer(model, config)
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
        
        for i, (idx, row) in enumerate(candidates.iterrows()):
            design_id = f"design_{start_id + i:04d}"
            
            # Convert row to dict for parameters
            params_dict = row.to_dict()
            
            try:
                # Instantiate parameters (validation happens here too)
                stent_params = StentParameters(**params_dict)
                generator = StentGenerator(stent_params)
                
                # Generate
                # We can skip full generation if we just want STEP, but StentGenerator.build() does it.
                # Assuming .export_step calls .build() internally if needed, or we call .build()
                # Looking at StentGenerator code... let's explicitly build if needed.
                # Actually export_step should handle it.
                
                out_path = cad_dir / f"{design_id}.step"
                generator.export_step(out_path)
                
                logger.info(f"  Generated {out_path.name}")
                
                # Record metadata
                entry = params_dict.copy()
                entry['design_id'] = design_id
                entry['cad_file'] = str(out_path)
                entry['status'] = 'pending_simulation'
                new_entries.append(entry)
                
            except Exception as e:
                logger.error(f"Failed to generate {design_id}: {e}")
        
        # Save Batch Manifest
        if new_entries:
            batch_df = pd.DataFrame(new_entries)
            batch_file = base_dir / f"batch_{start_id:04d}.csv"
            batch_df.to_csv(batch_file, index=False)
            logger.info(f"Saved batch manifest to {batch_file}")
            
            print("\n" + "="*50)
            print(f"NEXT STEPS for Batch {start_id}:")
            print(f"1. Run COMSOL simulation for designs listed in: {batch_file}")
            print(f"2. Append results to: {results_path}")
            print("="*50)

if __name__ == "__main__":
    main()
