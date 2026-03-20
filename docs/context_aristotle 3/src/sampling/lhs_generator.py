"""
Latin Hypercube Sampling (LHS) Generator.
"""

import numpy as np
import pandas as pd
from scipy.stats import qmc
from typing import Any, Optional

from src.utils.config import ConfigLoader

class LHSGenerator:
    """Generate design samples using Latin Hypercube Sampling."""
    
    def __init__(
        self,
        config: Optional[ConfigLoader] = None,
        seed: Optional[int] = 42,
        fixed_params: Optional[dict[str, Any]] = None,
    ):
        self.config = config or ConfigLoader()
        self.seed = seed
        self.fixed_params = fixed_params or {}

        unknown = sorted(set(self.fixed_params) - set(self.config.get_parameter_names()))
        if unknown:
            raise ValueError(f"Unknown fixed parameter override(s): {unknown}")
        
        self.param_names = [
            name for name in self.config.get_parameter_names()
            if name not in self.fixed_params
        ]
        self.bounds = self.config.get_bounds_list()
        self.n_dims = len(self.param_names)
        
        # Initialize sampler
        self.sampler = (
            qmc.LatinHypercube(d=self.n_dims, seed=self.seed)
            if self.n_dims > 0
            else None
        )
        
    def generate(self, n_samples: int, file_output: Optional[str] = None) -> pd.DataFrame:
        """
        Generate LHS samples.
        
        Args:
            n_samples: Number of samples to generate.
            file_output: Optional path to save CSV.
            
        Returns:
            DataFrame with sampled parameters in their physical ranges.
        """
        if self.n_dims > 0:
            # Generate samples in [0, 1]
            sample_01 = self.sampler.random(n=n_samples)

            # Scale to bounds
            lower_bounds = [self.config.design_vars[name].range[0] for name in self.param_names]
            upper_bounds = [self.config.design_vars[name].range[1] for name in self.param_names]

            sample_scaled = qmc.scale(sample_01, lower_bounds, upper_bounds)
            df = pd.DataFrame(sample_scaled, columns=self.param_names)
        else:
            df = pd.DataFrame(index=range(n_samples))

        for name, value in self.fixed_params.items():
            df[name] = value

        # Reorder to canonical parameter order so downstream manifests stay stable.
        df = df[self.config.get_parameter_names()]
        
        # Round discrete variables
        discrete_vars = self.config.get_discrete_vars()
        for var in discrete_vars:
            if var in df.columns:
                df[var] = df[var].round().astype(int)
            
        # Clip to ensure rounding didn't push out of bounds
        for var in self.config.get_parameter_names():
            min_val, max_val = self.config.design_vars[var].range
            df[var] = df[var].clip(min_val, max_val)
            
        if file_output:
            df.to_csv(file_output, index=False)
            
        return df
