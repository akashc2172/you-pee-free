"""
Tests for GP Trainer.
"""

import pytest
import pandas as pd
import numpy as np
from src.surrogate.training import GPTrainer

class TestGPTrainer:
    
    @pytest.fixture
    def synthetic_data(self):
        """Standard synthetic dataset."""
        X = np.random.rand(50, 2)
        y = np.sum(X, axis=1, keepdims=True) + 0.1 * np.random.randn(50, 1)
        
        df_X = pd.DataFrame(X, columns=['x1', 'x2'])
        df_y = pd.DataFrame(y, columns=['y'])
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
