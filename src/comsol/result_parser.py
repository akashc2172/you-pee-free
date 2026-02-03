"""
COMSOL Result Parser.
Parses simulation output CSVs and solver logs to extract metrics and diagnostics.
"""

from pathlib import Path
import pandas as pd
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

@dataclass
class COMSOLResult:
    run_id: str
    q_out: Optional[float] = None
    delta_p: Optional[float] = None
    q_sh: Dict[str, float] = None
    converged: bool = False
    iterations: int = 0
    cpu_time_s: float = 0.0
    mass_imbalance: Optional[float] = None
    errors: List[str] = None

class ResultParser:
    """Parses COMSOL outputs from a run directory."""
    
    def __init__(self):
        pass

    def parse_run(self, run_dir: Path, run_id: str) -> COMSOLResult:
        """
        Parse all outputs for a single run.
        
        Args:
            run_dir: Directory containing run outputs.
            run_id: Identifier for this simulation.
            
        Returns:
            COMSOLResult object.
        """
        run_dir = Path(run_dir)
        results_file = run_dir / f"{run_id}_results.csv"
        log_file = run_dir / f"{run_id}.log"
        
        # Initialize result container
        result = COMSOLResult(run_id=run_id, q_sh={}, errors=[])
        
        # 1. Parse Metrics (CSV)
        if results_file.exists():
            try:
                self._parse_metrics(results_file, result)
            except Exception as e:
                result.errors.append(f"Metrics parse error: {str(e)}")
        else:
            result.errors.append(f"Results file not found: {results_file.name}")
            
        # 2. Parse Log (TXT)
        if log_file.exists():
            try:
                self._parse_log(log_file, result)
            except Exception as e:
                result.errors.append(f"Log parse error: {str(e)}")
        else:
            result.errors.append(f"Log file not found: {log_file.name}")
            
        return result

    def _parse_metrics(self, file_path: Path, result: COMSOLResult):
        """Read CSV and extract scalar outputs."""
        # COMSOL export often has comments starting with %
        # Standard format: headers on one line, data on next
        df = pd.read_csv(file_path, comment='%')
        
        if df.empty:
            raise ValueError("Empty results file")
        
        # We assume the last row contains the final values (if strictly steady state)
        row = df.iloc[-1]
        
        # Extract known columns (case-insensitive keys for robustness)
        data = {k.lower().strip(): v for k, v in row.items()}
        
        # Q_out
        if 'q_out' in data:
            result.q_out = float(data['q_out'])
        elif 'q_total' in data:
            result.q_out = float(data['q_total'])
            
        # Delta P
        # Could be p_in - p_out or just dp
        if 'delta_p' in data:
            result.delta_p = float(data['delta_p'])
        elif 'dp' in data:
            result.delta_p = float(data['dp'])
            
        # Side hole flows
        # Expect columns like Q_prox, Q_mid, Q_dist OR Q_sh1, Q_sh2...
        for key, val in data.items():
            if key.startswith('q_sh') or key.startswith('q_prox') or key.startswith('q_mid') or key.startswith('q_dist'):
                result.q_sh[key] = float(val)

    def _parse_log(self, file_path: Path, result: COMSOLResult):
        """Scan solver log for convergence and performance info."""
        with open(file_path, 'r') as f:
            content = f.read()
            
        # 1. Check for convergence success message
        if "Solution time:" in content or "Solver finished." in content:
            result.converged = True
        
        # 2. Extract CPU time
        # Pattern: "Solution time: 123 s" or "Time: 123 s"
        time_match = re.search(r"Solution time:?\s*([\d\.]+(?:E[+-]?\d+)?)", content, re.IGNORECASE)
        if time_match:
            result.cpu_time_s = float(time_match.group(1))
            
        # 3. Iterations
        # Pattern: "Number of iterations: 42"
        iter_match = re.search(r"Number of iterations:?\s*(\d+)", content, re.IGNORECASE)
        if iter_match:
            result.iterations = int(iter_match.group(1))
            
        # 4. Check for obvious errors
        if "Error:" in content:
            # Extract first error line
            error_lines = [line.strip() for line in content.splitlines() if "Error:" in line]
            if error_lines:
                result.errors.append(error_lines[0])
