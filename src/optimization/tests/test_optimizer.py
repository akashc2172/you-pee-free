"""
Tests for Bayesian Optimizer.
"""

import pytest
import pandas as pd
import numpy as np
import torch
from unittest.mock import MagicMock

from src.optimization.optimizer import BayesianOptimizer
from src.surrogate.gp_model import GPModel
from src.utils.config import ConfigLoader

class TestBayesianOptimizer:
    
    @pytest.fixture
    def mock_model(self):
        # Create a real small GP model to avoid extensive mocking of BoTorch internals
        feature_names = ConfigLoader().get_parameter_names()
        n_features = len(feature_names)
        
        X = np.random.rand(10, n_features)
        y = np.random.rand(10, 2) # 2 outputs
        
        output_names = ['q_out', 'delta_p']
        
        df_X = pd.DataFrame(X, columns=feature_names)
        df_y = pd.DataFrame(y, columns=output_names)
        
        model = GPModel(input_dim=n_features, outcome_dim=2)
        model.fit(df_X, df_y)
        return model

    def test_init(self, mock_model):
        config = ConfigLoader()
        opt = BayesianOptimizer(mock_model, config)
        
        n_features = len(config.get_parameter_names())
        assert len(opt.feature_names) == n_features
        assert opt.bounds_df.shape == (2, n_features)

    def test_suggest(self, mock_model):
        config = ConfigLoader()
        opt = BayesianOptimizer(mock_model, config, weights={'q_out': 1.0, 'delta_p': 0.0})
        
        # Suggest 2 candidates
        candidates = opt.suggest(n_candidates=2)
        
        assert isinstance(candidates, pd.DataFrame)
        
        # It might return fewer than 2 if feasibility fails
        assert len(candidates) <= 2
        
        # Check bounds
        for col in candidates.columns:
            min_val = config.design_vars[col].range[0]
            max_val = config.design_vars[col].range[1]
            assert candidates[col].min() >= min_val - 1e-5
            assert candidates[col].max() <= max_val + 1e-5

    def test_denormalize(self, mock_model):
        config = ConfigLoader()
        opt = BayesianOptimizer(mock_model, config)
        
        n_features = len(opt.feature_names)
        # 0.5 in norm space should be mid-point of bounds
        x_norm = torch.ones(1, n_features, dtype=torch.double) * 0.5
        x_raw = opt._denormalize(x_norm)
        
        for i, col in enumerate(opt.feature_names):
            min_val = config.design_vars[col].range[0]
            max_val = config.design_vars[col].range[1]
            expected = (min_val + max_val) / 2
            assert np.isclose(x_raw[0, i].item(), expected)

    def test_resolve_effective_features_prefers_realized_hole_counts(self, mock_model):
        config = ConfigLoader()
        feature_names = config.get_parameter_names()
        df = pd.DataFrame([{k: config.design_vars[k].default for k in feature_names}])
        df["realized_n_prox"] = 1
        df["realized_n_mid"] = 2
        df["realized_n_dist"] = 3

        X = BayesianOptimizer.resolve_effective_features(df, feature_names)
        assert X.loc[0, "n_prox"] == 1
        assert X.loc[0, "n_mid"] == 2
        assert X.loc[0, "n_dist"] == 3
