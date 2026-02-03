"""
Feasibility filter for stent designs.
Applies hard constraints to reject invalid geometries.
"""

import pandas as pd
from typing import Tuple, Dict, Any
from dataclasses import dataclass

from src.cad.stent_generator import StentParameters
# We re-use StentParameters validation logic

@dataclass
class FeasibilityReport:
    n_input: int
    n_valid: int
    rejection_reasons: Dict[str, int]
    valid_indices: list

class FeasibilityFilter:
    """Filter designs based on hard geometric constraints."""
    
    def __init__(self):
        pass
        
    def filter(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, FeasibilityReport]:
        """
        Apply constraints to a batch of designs.
        
        Args:
            df: DataFrame of design parameters.
            
        Returns:
            (valid_df, FeasibilityReport)
        """
        valid_rows = []
        rejection_reasons = {}
        valid_indices = []
        
        for idx, row in df.iterrows():
            reason = self._check_row(row)
            if reason is None:
                valid_rows.append(row)
                valid_indices.append(idx)
            else:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        
        if valid_rows:
            valid_df = pd.DataFrame(valid_rows).reset_index(drop=True)
            # Ensure integer columns are preserved
            for col in df.columns:
                if pd.api.types.is_integer_dtype(df[col]):
                    valid_df[col] = valid_df[col].astype(int)
        else:
            valid_df = pd.DataFrame(columns=df.columns)
            
        report = FeasibilityReport(
            n_input=len(df),
            n_valid=len(valid_df),
            rejection_reasons=rejection_reasons,
            valid_indices=valid_indices
        )
        
        return valid_df, report
    
    def _check_row(self, row: pd.Series) -> Any:
        """
        Check a single row. Returns None if valid, else error string.
        """
        try:
            # We use StentParameters validation logic
            # Map row to StentParameters args
            # Note: StentParameters expects specific names.
            # Our parameters.yaml naming mostly matches StentParameters fields 
            # (stent_french, stent_length, etc.)
            
            # Extract args ignoring extra cols if any
            params_dict = row.to_dict()
            
            # Filter dict to only known fields of StentParameters to be safe,
            # or rely on python ignoring extra kwargs if we unpack carefully.
            # StentParameters is a dataclass, so it doesn't accept extra kwargs by default.
            
            # Need to map or select valid keys.
            # Valid keys from StentParameters.__init__
            valid_keys = StentParameters.__dataclass_fields__.keys()
            filtered_args = {k: v for k, v in params_dict.items() if k in valid_keys}
            
            # Instantiate (triggers validation)
            StentParameters(**filtered_args)
            
            return None
            
        except ValueError as e:
            # Extract main reason (e.g. "ID", "Middle section", "Cannot fit")
            msg = str(e)
            if "ID" in msg and "ID_MIN" in msg:
                return "ID < ID_MIN"
            elif "Middle section" in msg:
                return "Middle section too short"
            elif "Cannot fit" in msg:
                if "prox" in msg: return "Hole packing (prox)"
                if "mid" in msg: return "Hole packing (mid)"
                if "dist" in msg: return "Hole packing (dist)"
                return "Hole packing (other)"
            else:
                return "Other: " + msg.split('.')[0]
        except Exception as e:
            return f"Unknown error: {str(e)}"
