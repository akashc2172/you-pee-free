"""
Training pipeline for GP surrogates.
"""

import pandas as pd
import numpy as np
import torch
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

from src.surrogate.gp_model import GPModel

class GPTrainer:
    """Trains and validates GP models."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir) if output_dir else Path("data/surrogate_models")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def train(self, 
              X: pd.DataFrame, 
              y: pd.DataFrame, 
              test_size: float = 0.2,
              random_state: int = 42) -> Tuple[GPModel, Dict]:
        """
        Train a model on the full provided dataset (or split).
        For production, we usually train on all available data.
        
        Args:
            X: Input features
            y: Target outputs
            
        Returns:
            (model, metrics)
        """
        model = GPModel(input_dim=X.shape[1], outcome_dim=y.shape[1])
        model.fit(X, y)
        
        # In-sample metrics
        metrics = self.evaluate(model, X, y, prefix="train")
        
        return model, metrics

    def cross_validate(self, 
                       X: pd.DataFrame, 
                       y: pd.DataFrame, 
                       k_folds: int = 5) -> pd.DataFrame:
        """
        Perform K-Fold Cross Validation.
        
        Returns:
            DataFrame of metrics per fold.
        """
        kf = KFold(n_splits=k_folds, shuffle=True, random_state=42)
        results = []
        
        for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            
            # Train
            model = GPModel(input_dim=X.shape[1], outcome_dim=y.shape[1])
            model.fit(X_train, y_train)
            
            # Evaluate
            metrics = self.evaluate(model, X_val, y_val, prefix="val")
            metrics['fold'] = fold
            results.append(metrics)
            
        return pd.DataFrame(results)

    def evaluate(self, 
                 model: GPModel, 
                 X: pd.DataFrame, 
                 y: pd.DataFrame, 
                 prefix: str = "test") -> Dict[str, float]:
        """
        Evaluate model performance.
        Computes R2, RMSE, MAE, and NLPD (Negative Log Predictive Density).
        """
        mean, var = model.predict(X)
        y_true = y.values
        
        # Error metrics (averaged over outputs)
        mse = mean_squared_error(y_true, mean)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_true, mean)
        r2 = r2_score(y_true, mean)
        
        # NLPD (Gaussian assumption)
        # NLPD = 0.5 * (log(2*pi*var) + (y - mu)^2 / var)
        # Average over N samples and M outputs
        nll_term = 0.5 * (np.log(2 * np.pi * var) + ((y_true - mean)**2) / var)
        nlpd = np.mean(nll_term)
        
        return {
            f"{prefix}_rmse": rmse,
            f"{prefix}_mae": mae,
            f"{prefix}_r2": r2,
            f"{prefix}_nlpd": nlpd
        }

    def save_model(self, model: GPModel, name: str):
        path = self.output_dir / f"{name}.pt"
        model.save(path)
