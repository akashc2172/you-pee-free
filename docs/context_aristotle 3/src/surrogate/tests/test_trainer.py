"""
Tests for GP Trainer.
"""

import pytest
import pandas as pd
import numpy as np
from src.surrogate.training import GPTrainer
from src.surrogate.output_schema import SCHEMA_V1, tier1_target_columns

class TestGPTrainer:
    
    @pytest.fixture
    def synthetic_data(self):
        """Standard synthetic dataset."""
        X = np.random.rand(50, 2)
        y_scalar = np.sum(X, axis=1, keepdims=True) + 0.1 * np.random.randn(50, 1)
        
        df_X = pd.DataFrame(X, columns=['x1', 'x2'])
        # Build schema-compliant Tier-1 transformed outputs (synthetic but well-posed).
        # These tests validate the trainer wiring, not CFD realism.
        df_y = pd.DataFrame(
            {
                "log_deltaP": y_scalar[:, 0],
                "log_Q_out": y_scalar[:, 0] + 0.1,
                "log_Ex": y_scalar[:, 0] - 0.1,
                "logit_centroid_norm": y_scalar[:, 0] * 0.0,
                "logit_IQS": y_scalar[:, 0] * 0.0,
            }
        )[tier1_target_columns(include_optional=False, schema=SCHEMA_V1)]
        return df_X, df_y

    def test_train_structure(self, synthetic_data, tmp_path):
        X, y = synthetic_data
        trainer = GPTrainer(output_dir=tmp_path)
        
        model, metrics = trainer.train(X, y)
        
        assert model is not None
        assert "train_rmse" in metrics
        assert metrics["train_r2"] < 1.0 # Should have some error due to noise

    def test_cross_validate(self, synthetic_data):
        X, y = synthetic_data
        trainer = GPTrainer()
        
        results = trainer.cross_validate(X, y, k_folds=3)
        
        assert len(results) == 3
        assert "val_rmse" in results.columns
        assert "val_nlpd" in results.columns
        
        mean_r2 = results['val_r2'].mean()
        assert mean_r2 > 0.0 # Should be better than dummy

    def test_save_model(self, synthetic_data, tmp_path):
        X, y = synthetic_data
        trainer = GPTrainer(output_dir=tmp_path)
        model, _ = trainer.train(X, y)
        
        trainer.save_model(model, "test_model")
        assert (tmp_path / "test_model.pt").exists()
