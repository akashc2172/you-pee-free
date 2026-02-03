"""
Bayesian Optimizer using BoTorch.
"""

import torch
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Callable, Tuple
from pathlib import Path

from botorch.acquisition import qExpectedImprovement
from botorch.optim import optimize_acqf
from botorch.acquisition.objective import ScalarizedPosteriorTransform

from src.surrogate.gp_model import GPModel
from src.sampling.feasibility import FeasibilityFilter
from src.utils.config import ConfigLoader

class BayesianOptimizer:
    """
    Bayesian Optimizer for Stent Design.
    """
    
    def __init__(self, 
                 model: GPModel, 
                 config: ConfigLoader,
                 weights: Optional[Dict[str, float]] = None):
        """
        Args:
            model: Trained GPModel
            config: ConfigLoader with parameter bounds
            weights: Objective weights (e.g. {'Q_out': 1.0, 'delta_P': -0.01})
        """
        self.model = model
        self.config = config
        self.weights = weights or {'q_out': 1.0, 'delta_p': -0.001} # Default: Max flow, min pressure
        
        self.feasibility = FeasibilityFilter()
        
        # Get bounds from config
        self.feature_names = config.get_parameter_names()
        bounds_data = {name: config.design_vars[name].range for name in self.feature_names}
        self.bounds_df = pd.DataFrame(bounds_data, index=['min', 'max'])
        
        # Convert bounds to tensor for BoTorch
        # Note: GPModel expects NORMALIZED inputs [0,1] if it uses Normalize
        # BUT our GPModel (manual) handles raw inputs internally if we pass raw to predict.
        # BoTorch optimize_acqf expects bounds in the input space of the model.
        # Since our GPModel wraps manual normalization, we need to be careful.
        # We should optimize in the NORMALIZED space [0,1] and then denormalize.
        
        # Actually my new GPModel.model expects NORMALIZED inputs.
        # So bounds should be [0, 1] for all dims.
        self.norm_bounds = torch.stack([
            torch.zeros(len(self.feature_names)),
            torch.ones(len(self.feature_names))
        ]).to(model.device).double()
        
    def suggest(self, n_candidates: int = 1) -> pd.DataFrame:
        """
        Suggest new candidates.
        
        1. Optimize Scalarized qEI in normalized space.
        2. Denormalize candidates.
        3. Filter for feasibility.
        4. If not enough, repeat or return what we have.
        """
        if self.model.model is None:
            raise RuntimeError("Model must be fit before optimization")
            
        # Define Objective
        # We map the multi-output GP output to a scalar
        # Weights tensor needs to match output dim of model
        # Assuming GP outputs are sorted by column name... risky.
        # Let's assume the user/trainer ensures y_train columns match weights keys order?
        # Better: we can't easily know the column mapping inside GPModel unless we stored it.
        # For now, let's assume the weights provided match indices: 0 -> Q_out, 1 -> delta_P
        # User must ensure y_train passed to fit matches this.
        
        # Weights tensor
        weights_list = [self.weights.get(k, 0.0) for k in ['q_out', 'delta_p']] # Example
        # TODO: Make this robust by storing column names in GPModel
        
        weights_t = torch.tensor(weights_list, device=self.model.device, dtype=torch.double)
        objective = ScalarizedPosteriorTransform(weights=weights_t)
        
        # Acquisition Function
        acq_func = qExpectedImprovement(
            model=self.model.model,
            best_f=self._get_best_f(objective),
            posterior_transform=objective
        )
        
        # Optimize
        # We ask for more raw samples to handle feasibility rejection
        candidates_norm, _ = optimize_acqf(
            acq_function=acq_func,
            bounds=self.norm_bounds,
            q=n_candidates * 10, # Oversample
            num_restarts=10,
            raw_samples=512,  # Increased raw samples
        )
        
        # Denormalize
        candidates_raw_t = self._denormalize(candidates_norm)
        candidates_df = pd.DataFrame(
            candidates_raw_t.cpu().detach().numpy(), 
            columns=self.feature_names
        )
        
        # Filter
        valid_df, _ = self.feasibility.filter(candidates_df)
        
        if len(valid_df) < n_candidates:
            print(f"Warning: Only found {len(valid_df)} valid candidates (requested {n_candidates})")
            return valid_df
            
        return valid_df.iloc[:n_candidates]

    def _get_best_f(self, objective):
        """Calculate best scalarized objective value from training data."""
        # Evaluate posterior mean on training data
        # model.train_inputs is (1, N, D)
        train_x = self.model.model.train_inputs[0]
        with torch.no_grad():
            posterior = self.model.model.posterior(train_x)
            # Apply objective
            vals = objective(posterior).mean
        return vals.max()

    def _denormalize(self, X_norm: torch.Tensor) -> torch.Tensor:
        """Convert [0,1] tensor to raw parameter space."""
        # x_raw = x_norm * (max - min) + min
        lower = torch.tensor(self.bounds_df.loc['min'].values, device=X_norm.device, dtype=torch.double)
        upper = torch.tensor(self.bounds_df.loc['max'].values, device=X_norm.device, dtype=torch.double)
        return X_norm * (upper - lower) + lower
