"""
Latin Hypercube Sampling (LHS) Generator.
"""

import numpy as np
import pandas as pd
from scipy.stats import qmc
from typing import Optional

from src.utils.config import ConfigLoader

class LHSGenerator:
    """Generate design samples using Latin Hypercube Sampling."""
    
    def __init__(self, config: Optional[ConfigLoader] = None, seed: Optional[int] = 42):
        self.config = config or ConfigLoader()
        self.seed = seed
        
        self.param_names = self.config.get_parameter_names()
        self.bounds = self.config.get_bounds_list()
        self.n_dims = len(self.param_names)
        
        # Initialize sampler
        self.sampler = qmc.LatinHypercube(d=self.n_dims, seed=self.seed)
        
    def generate(self, n_samples: int, file_output: Optional[str] = None) -> pd.DataFrame:
        """
        Generate LHS samples.
        
        Args:
            n_samples: Number of samples to generate.
            file_output: Optional path to save CSV.
            
        Returns:
            DataFrame with sampled parameters in their physical ranges.
        """
        # Generate samples in [0, 1]
        sample_01 = self.sampler.random(n=n_samples)
        
        # Scale to bounds
        lower_bounds = [b[0] for b in self.bounds]
        upper_bounds = [b[1] for b in self.bounds]
        
        sample_scaled = qmc.scale(sample_01, lower_bounds, upper_bounds)
        
        df = pd.DataFrame(sample_scaled, columns=self.param_names)
        
        # Round discrete variables
        discrete_vars = self.config.get_discrete_vars()
        for var in discrete_vars:
            df[var] = df[var].round().astype(int)
            
        # Clip to ensure rounding didn't push out of bounds
        for var in self.param_names:
            min_val, max_val = self.config.design_vars[var].range
            df[var] = df[var].clip(min_val, max_val)
            
        if file_output:
            df.to_csv(file_output, index=False)
            
        return df
