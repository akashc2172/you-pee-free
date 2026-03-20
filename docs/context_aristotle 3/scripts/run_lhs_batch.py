#!/usr/bin/env python3
"""
Generate an LHS batch of stent designs and apply feasibility filtering.

Usage:
    python scripts/run_lhs_batch.py --n_samples 60 --seed 42 --output data/lhs_batches/batch_001.csv
"""

import argparse
from pathlib import Path
import sys
import logging

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.sampling.lhs_generator import LHSGenerator
from src.sampling.feasibility import FeasibilityFilter
from src.utils.logging_utils import setup_simple_logging

def main():
    parser = argparse.ArgumentParser(description="Generate Stent LHS Batch")
    parser.add_argument('--n_samples', type=int, default=60, help="Target number of valid samples")
    parser.add_argument('--seed', type=int, default=None, help="Random seed")
    parser.add_argument('--output', type=str, required=True, help="Output CSV path")
    parser.add_argument('--oversample', type=float, default=3.0, help="Oversampling factor")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = logging.getLogger("LHS_Batch")
    setup_simple_logging()
    
    # Calculate raw count
    n_raw = int(args.n_samples * args.oversample)
    logger.info(f"Generating {n_raw} raw samples (Target: {args.n_samples}, Factor: {args.oversample}x)")
    
    # 1. Generate
    gen = LHSGenerator(seed=args.seed)
    raw_df = gen.generate(n_samples=n_raw)
    
    # 2. Filter
    filt = FeasibilityFilter()
    valid_df, report = filt.filter(raw_df)
    
    logger.info(f"Feasibility Logic Complete:")
    logger.info(f"  Input: {report.n_input}")
    logger.info(f"  Valid: {report.n_valid} ({100*report.n_valid/report.n_input:.1f}%)")
    logger.info(f"  Rejections: {report.rejection_reasons}")
    
    # 3. Truncate to requested size if we have enough
    if len(valid_df) >= args.n_samples:
        final_df = valid_df.iloc[:args.n_samples]
        logger.info(f"Truncating to requested {args.n_samples} samples.")
    else:
        final_df = valid_df
        logger.warning(f"Could only generate {len(final_df)} valid samples (requested {args.n_samples}). Increase oversample factor.")
    
    # 4. Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(out_path, index=False)
    logger.info(f"Saved batch to {out_path}")

if __name__ == "__main__":
    main()
