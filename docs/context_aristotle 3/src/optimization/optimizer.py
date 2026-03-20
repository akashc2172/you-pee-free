"""
Bayesian Optimizer using BoTorch.
"""

import torch
import pandas as pd
import numpy as np
from typing import Any, List, Dict, Optional, Callable, Tuple
from pathlib import Path

from botorch.acquisition import qExpectedImprovement
from botorch.optim import optimize_acqf
from botorch.acquisition.objective import ScalarizedPosteriorTransform

from src.surrogate.gp_model import GPModel
from src.sampling.feasibility import FeasibilityFilter
from src.utils.config import ConfigLoader
from src.surrogate.output_schema import SCHEMA_V1, tier1_target_columns

class BayesianOptimizer:
    """
    Bayesian Optimizer for Stent Design.
    """
    
    def __init__(self, 
                 model: GPModel, 
                 config: ConfigLoader,
                 weights: Optional[Dict[str, float]] = None,
                 fixed_params: Optional[Dict[str, Any]] = None):
        """
        Args:
            model: Trained GPModel
            config: ConfigLoader with parameter bounds
            weights: Objective weights (e.g. {'Q_out': 1.0, 'delta_P': -0.01})
        """
        self.model = model
        self.config = config
        # Default weights in the *transformed Tier-1 space*.
        # Positive = maximize, negative = minimize.
        self.weights = weights or {
            "log_Q_out": 1.0,
            "log_deltaP": -0.25,
            "log_Ex": 0.25,
            # localization terms default to 0 (not scalarized) unless user opts in
            "logit_centroid_norm": 0.0,
            "logit_IQS": 0.0,
        }
        self.fixed_params = fixed_params or {}

        self.feasibility = FeasibilityFilter()
        
        # Get bounds from config
        self.feature_names = [
            name for name in config.get_parameter_names()
            if name not in self.fixed_params
        ]
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
        if not self.model.y_columns:
            raise RuntimeError("Model is missing y_columns; train using GPTrainer + schema assembly")
            
        # Define Objective
        # Resolve weights by metric name against model.y_columns (schema-driven).
        y_cols = list(self.model.y_columns)
        missing = [k for k in self.weights.keys() if k not in y_cols]
        if missing:
            raise ValueError(
                "Optimizer weights reference outputs not present in the trained model. "
                f"missing={missing} model_outputs={y_cols}"
            )
        weights_list = [float(self.weights.get(name, 0.0)) for name in y_cols]
        if all(abs(w) < 1e-15 for w in weights_list):
            raise ValueError("All optimizer weights are zero; provide at least one nonzero weight")

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
        if self.feature_names:
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
        else:
            candidates_df = pd.DataFrame(index=range(n_candidates * 10))

        candidates_df = self._apply_fixed_params(candidates_df)
        
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

    def _apply_fixed_params(self, df: pd.DataFrame) -> pd.DataFrame:
        """Stamp fixed campaign-level parameters into every suggested candidate."""
        for name, value in self.fixed_params.items():
            df[name] = value
        ordered = [name for name in self.config.get_parameter_names() if name in df.columns]
        return df[ordered]

    @staticmethod
    def resolve_effective_features(df: pd.DataFrame, feature_names: List[str]) -> pd.DataFrame:
        """Prefer realized hole counts when present, fallback to requested."""
        X = df[feature_names].copy()
        mapping = {
            "n_prox": "realized_n_prox",
            "n_mid": "realized_n_mid",
            "n_dist": "realized_n_dist",
            "requested_midsection_hole_count": "realized_midsection_hole_count",
            # Future-proof mappings when additional realized geometry features
            # are promoted into the sampled/training feature set.
            "requested_body_holes": "realized_body_holes",
            "requested_coil_hole_count": "realized_coil_hole_count",
            "requested_total_hole_count": "realized_total_hole_count",
            "body_hole_total_area": "realized_body_hole_total_area",
            "total_hole_area": "realized_total_hole_area",
            "body_hole_min_spacing": "realized_body_hole_min_spacing",
            "body_hole_mean_spacing": "realized_body_hole_mean_spacing",
            "nearest_neighbor_spacing": "realized_nearest_neighbor_spacing",
            "arc_positions": "realized_arc_positions",
        }
        for base, realized in mapping.items():
            if base in X.columns and realized in df.columns:
                X[base] = df[realized]

        # Alternate realized feature names exported by COMSOL scripts.
        if "n_mid" in X.columns and "realized_midsection_hole_count" in df.columns:
            X["n_mid"] = df["realized_midsection_hole_count"]
        return X
