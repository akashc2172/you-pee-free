#!/usr/bin/env python3
"""
Generate a single, basic, symmetrical stent.
"""

from pathlib import Path
import sys
import logging

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cad.stent_generator import StentGenerator, StentParameters, StlExportOptions
from src.utils.logging_utils import setup_simple_logging

def main():
    setup_simple_logging()
    logger = logging.getLogger("BasicStent")

    base_dir = Path("data/basic_stent")
    base_dir.mkdir(parents=True, exist_ok=True)

    # Basic symmetrical parameters that match defaults explicitly
    params = StentParameters(
        stent_french=6.0,
        stent_length=150.0,
        
        # Coil geometry is frozen by default in StentParameters
        # (fixed radius/pitch/turns for this campaign stage).
        section_length_prox=30.0,
        n_prox=3,
        section_length_dist=30.0,
        n_dist=3,
        
        # Middle Section (derived length = 90.0)
        n_mid=6,
        
        # General Fractions
        r_t=0.15,
        r_sh=0.40,
        r_end=0.60,
        
        # Standard ends
        unroofed_length=0.0
    )

    logger.info("Initializing Stent Generator with symmetrical parameters...")
    gen = StentGenerator(params)

    # Output paths
    step_path = base_dir / "basic_stent.step"
    stl_path = base_dir / "basic_stent.stl"

    # Export STEP
    logger.info(f"Generating STEP at {step_path}...")
    gen.export_step(step_path)
    
    # Export STL w/ QA
    logger.info(f"Generating STL w/ QA at {stl_path} (Standard Quality)...")
    stl_opts = StlExportOptions.from_profile("standard", validate_mesh=False)
    stl_meta = gen.export_stl(stl_path, options=stl_opts)

    # Summary
    qa_pass = stl_meta['qa']['passed'] if stl_meta.get('qa') else None
    
    logger.info("\n=== GENERATION SUMMARY ===")
    logger.info(f"File: {step_path}")
    logger.info(f"File: {stl_path}")
    logger.info(f"Mesh QA Passed: {qa_pass}")
    for key, value in gen.get_info().items():
        logger.info(f"  {key}: {value}")

if __name__ == "__main__":
    main()
