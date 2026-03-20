"""
Gaussian Process Model Wrapper using BoTorch.
"""

import torch
import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple, List, Sequence
from pathlib import Path

from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.kernels import MaternKernel, ScaleKernel
from gpytorch.likelihoods import GaussianLikelihood

class GPModel:
    """
    Gaussian Process Surrogate Model.
    Wraps BoTorch SingleTaskGP for easy training and prediction.
    Uses manual normalization/standardization to ensure stability.
    """
    
    def __init__(self, 
                 input_dim: int,
                 outcome_dim: int,
                 kernel_type: str = "matern2.5",
                 device: str = "cpu"):
        
        self.input_dim = input_dim
        self.outcome_dim = outcome_dim
        self.kernel_type = kernel_type
        # Use float64 for better stability
        self.device = torch.device(device)
        self.dtype = torch.double 
        
        self.model = None
        self.mll = None
        
        # Scaling parameters
        self.x_min = None
        self.x_max = None
        self.y_mean = None
        self.y_std = None

        # Column name contracts (schema-driven, not optional once fit)
        self.x_columns: Optional[List[str]] = None
        self.y_columns: Optional[List[str]] = None
        
    def _normalize_x(self, X: torch.Tensor) -> torch.Tensor:
        return (X - self.x_min) / (self.x_max - self.x_min + 1e-8)
        
    def _standardize_y(self, Y: torch.Tensor) -> torch.Tensor:
        return (Y - self.y_mean) / (self.y_std + 1e-8)
        
    def _unstandardize_y(self, Y: torch.Tensor) -> torch.Tensor:
        return Y * (self.y_std + 1e-8) + self.y_mean

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.DataFrame,
        *,
        x_columns: Optional[Sequence[str]] = None,
        y_columns: Optional[Sequence[str]] = None,
    ):
        """
        Fit the GP model to training data.
        """
        if x_columns is not None and list(x_columns) != list(X_train.columns):
            raise ValueError("x_columns does not match X_train.columns")
        if y_columns is not None and list(y_columns) != list(y_train.columns):
            raise ValueError("y_columns does not match y_train.columns")

        self.x_columns = list(X_train.columns)
        self.y_columns = list(y_train.columns)

        # Convert to tensors
        train_X = torch.tensor(X_train.values, dtype=self.dtype, device=self.device)
        train_Y = torch.tensor(y_train.values, dtype=self.dtype, device=self.device)
        
        # Compute scaling stats
        self.x_min = train_X.min(dim=0)[0]
        self.x_max = train_X.max(dim=0)[0]
        self.y_mean = train_Y.mean(dim=0)
        self.y_std = train_Y.std(dim=0)
        
        # Scale data
        train_X_norm = self._normalize_x(train_X)
        train_Y_scaled = self._standardize_y(train_Y)
        
        # Initialize model with manual scaling
        covar_module = None
        if self.kernel_type == "matern2.5":
            covar_module = ScaleKernel(
                MaternKernel(nu=2.5, ard_num_dims=self.input_dim)
            )
        
        self.model = SingleTaskGP(
            train_X_norm, 
            train_Y_scaled,
            covar_module=covar_module
            # No input/outcome transform, we did it manually
        )
        
        self.mll = ExactMarginalLogLikelihood(self.model.likelihood, self.model)
        
        # Fit hyperparameters
        fit_gpytorch_mll(self.mll)
        
    def predict(self, X_test: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict mean and variance.
        """
        if self.model is None:
            raise RuntimeError("Model not fit yet")
        if self.x_columns is not None and list(X_test.columns) != list(self.x_columns):
            raise ValueError(
                "X_test columns do not match training columns. "
                f"expected={self.x_columns}, got={list(X_test.columns)}"
            )
            
        self.model.eval()
        self.model.likelihood.eval()
        
        test_X = torch.tensor(X_test.values, dtype=self.dtype, device=self.device)
        test_X_norm = self._normalize_x(test_X)
        
        with torch.no_grad():
            posterior = self.model(test_X_norm)
            # Predictions are in standardized space
            mean_scaled = posterior.mean
            var_scaled = posterior.variance

            # BoTorch may return multi-output as (M, N) (batched) rather than (N, M).
            n = int(test_X_norm.shape[0])
            if mean_scaled.ndim == 2 and mean_scaled.shape[0] == self.outcome_dim and mean_scaled.shape[1] == n:
                mean_scaled = mean_scaled.transpose(-2, -1)
            if var_scaled.ndim == 2 and var_scaled.shape[0] == self.outcome_dim and var_scaled.shape[1] == n:
                var_scaled = var_scaled.transpose(-2, -1)
            
            # Un-standardize mean
            mean = self._unstandardize_y(mean_scaled)
            # Un-standardize variance: var = var_scaled * std^2
            var = var_scaled * (self.y_std ** 2 + 1e-8)
            
        # Ensure (N, M) shape
        mean_np = mean.cpu().numpy()
        var_np = var.cpu().numpy()
        
        if mean_np.ndim == 1:
            mean_np = mean_np[:, None]
        if var_np.ndim == 1:
            var_np = var_np[:, None]
            
        return mean_np, var_np
        
    def save(self, path: Path):
        """Save model state dict and scaling params."""
        if self.model is None:
            raise RuntimeError("Model not fit")
        
        state = {
            'model_state': self.model.state_dict(),
            'scaling': {
                'x_min': self.x_min,
                'x_max': self.x_max,
                'y_mean': self.y_mean,
                'y_std': self.y_std
            },
            "columns": {
                "x_columns": self.x_columns,
                "y_columns": self.y_columns,
            },
            "schema_version": "gp_model_state_v1",
        }
        torch.save(state, path)
        
    def load(self, path: Path, X_sample: pd.DataFrame, y_sample: pd.DataFrame):
        """Load model state."""
        state = torch.load(path)
        scaling = state['scaling']
        columns = state.get("columns", {}) or {}
        
        # Restore scaling
        self.x_min = scaling['x_min']
        self.x_max = scaling['x_max']
        self.y_mean = scaling['y_mean']
        self.y_std = scaling['y_std']
        self.x_columns = columns.get("x_columns")
        self.y_columns = columns.get("y_columns")
        
        # Re-init structure (needs sample data to set dimensions, but we can pass dummy)
        # However, BoTorch model init requires data to set input/outcome transforms (if used)
        # OR just training data shapes.
        # Since we manual scale, we just need correct shapes.
        
        # Hack: Init with sample data scaled by loaded params
        X_sample_torch = torch.tensor(X_sample.values, dtype=self.dtype, device=self.device)
        y_sample_torch = torch.tensor(y_sample.values, dtype=self.dtype, device=self.device)
        
        X_norm = self._normalize_x(X_sample_torch)
        y_scaled = self._standardize_y(y_sample_torch)
        
        covar_module = None
        if self.kernel_type == "matern2.5":
            covar_module = ScaleKernel(
                MaternKernel(nu=2.5, ard_num_dims=self.input_dim)
            )
            
        self.model = SingleTaskGP(X_norm, y_scaled, covar_module=covar_module)
        self.model.load_state_dict(state['model_state'])
        self.model.eval()
