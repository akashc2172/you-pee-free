"""
Tests for GP Surrogate Model.
"""

import pytest
import pandas as pd
import numpy as np
import torch
from pathlib import Path

from src.surrogate.gp_model import GPModel

class TestGPModel:
    
    @pytest.fixture
    def synthetic_data(self):
        """Generate simple linear y = x1 + x2 data."""
        X = np.random.rand(50, 2) # 50 samples, 2 features
        y = np.sum(X, axis=1, keepdims=True)
        
        feature_names = ['x1', 'x2']
        output_names = ['y']
        
        df_X = pd.DataFrame(X, columns=feature_names)
        df_y = pd.DataFrame(y, columns=output_names)
        
        return df_X, df_y

    def test_fit_predict(self, synthetic_data):
        X, y = synthetic_data
        
        model = GPModel(input_dim=2, outcome_dim=1)
        model.fit(X, y)
        
        # Predict on training data
        mean, var = model.predict(X)
        
        assert mean.shape == (50, 1)
        assert var.shape == (50, 1)
        
        # Check if R2 is decent (it should be for this simple case)
        # Note: GP fits exact on noise-free data if we don't fix noise
        from sklearn.metrics import r2_score
        r2 = r2_score(y, mean)
        assert r2 > 0.9

    def test_save_load(self, synthetic_data, tmp_path):
        X, y = synthetic_data
        model = GPModel(input_dim=2, outcome_dim=1)
        model.fit(X, y)
        
        save_path = tmp_path / "model.pt"
        model.save(save_path)
        
        # Load new model
        new_model = GPModel(input_dim=2, outcome_dim=1)
        new_model.load(save_path, X, y)
        
        mean1, _ = model.predict(X)
        mean2, _ = new_model.predict(X)
        
        np.testing.assert_allclose(mean1, mean2, atol=1e-5)
