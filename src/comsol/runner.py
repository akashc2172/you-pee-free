"""
COMSOL Runner.
Manages the execution of COMSOL batch commands.
"""

from pathlib import Path
import subprocess
import logging
import pandas as pd
from typing import Dict, List, Optional
import os
import shutil

class COMSOLRunner:
    """Executes COMSOL simulations."""
    
    def __init__(self, 
                 comsol_exec: str = "comsol", 
                 base_mph: Optional[Path] = None,
                 output_dir: Optional[Path] = None):
        
        self.comsol_exec = comsol_exec  # Path to 'comsol' binary
        self.base_mph = Path(base_mph) if base_mph else None
        self.output_dir = Path(output_dir) if output_dir else Path("data/comsol_results")
        self.logger = logging.getLogger("COMSOLRunner")
        
    def run_batch(self, 
                  design_id: str, 
                  parameters: Dict[str, float], 
                  cad_file: Path) -> Path:
        """
        Run a single simulation in batch mode.
        
        Args:
            design_id: Unique ID for this run.
            parameters: Dictionary of global parameters to update.
            cad_file: Path to the specific STEP file geometry.
            
        Returns:
            Path to the run directory.
        """
        if not self.base_mph or not self.base_mph.exists():
            raise FileNotFoundError(f"Base MPH file not found: {self.base_mph}")
            
        # Create run directory
        run_dir = self.output_dir / design_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # COMSOL Batch Command Construction
        # comsol batch -input base.mph -output out.mph -pname "p1,p2" -pval "v1,v2"
        # We also need to point to the correct CAD file. 
        # Usually this is done via a LiveLink parameter or a file import parameter.
        # Let's assume there is a parameter 'cad_filename' that we point to the STEP file.
        
        # Prepare parameters
        # Add CAD file path to parameters (needs to be absolute string)
        parameters['cad_path'] = str(cad_file.resolve())
        parameters['design_id'] = design_id
        
        pnames = []
        pvals = []
        for k, v in parameters.items():
            pnames.append(k)
            pvals.append(str(v))
            
        pname_str = ",".join(pnames)
        pval_str = ",".join(pvals)
        
        output_mph = run_dir / f"{design_id}.mph"
        log_file = run_dir / f"{design_id}.log"
        results_file = run_dir / f"{design_id}_results.csv" # Expected export
        
        cmd = [
            self.comsol_exec,
            "batch",
            "-input", str(self.base_mph),
            "-output", str(output_mph),
            "-pname", pname_str,
            "-pval", pval_str,
            "-batchlog", str(log_file)
        ]
        
        self.logger.info(f"Starting run {design_id}")
        self.logger.debug(f"Command: {' '.join(cmd)}")
        
        try:
            # We run synchronously for now. Parallelism can be handled by a queue worker.
            subprocess.run(cmd, check=True, capture_output=True)
            self.logger.info(f"Run {design_id} completed.")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Run {design_id} failed with code {e.returncode}")
            # Ensure log is preserved even on failure
            if e.stderr:
                with open(run_dir / "stderr.log", "w") as f:
                    f.write(e.stderr.decode())
            raise e
            
        return run_dir
        
    def generate_batch_script(self, design_df: pd.DataFrame, cad_dir: Path, script_path: Path):
        """
        Generate a shell script to run all designs sequentially (or parallel via GNU parallel).
        Useful for running on a cluster.
        """
        lines = ["#!/bin/bash", "mkdir -p data/comsol_results"]
        
        for idx, row in design_df.iterrows():
            did = f"design_{idx:03d}"
            # Logic similar to run_batch but writing to string...
            # Left as placeholder for future cluster deployment
            pass
