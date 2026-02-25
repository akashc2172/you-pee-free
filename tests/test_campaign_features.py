import pandas as pd

from scripts.run_optimization_campaign import resolve_effective_training_features
from src.utils.config import ConfigLoader


def test_resolve_effective_training_features_fallback_and_override():
    cfg = ConfigLoader()
    feature_names = cfg.get_parameter_names()

    row = {k: cfg.design_vars[k].default for k in feature_names}
    df = pd.DataFrame([row])

    # Fallback with no realized columns.
    X0 = resolve_effective_training_features(df, feature_names)
    assert X0.loc[0, "n_prox"] == row["n_prox"]

    # Override when realized columns exist.
    df["realized_n_prox"] = 1
    df["realized_n_mid"] = 2
    df["realized_n_dist"] = 3
    X1 = resolve_effective_training_features(df, feature_names)
    assert X1.loc[0, "n_prox"] == 1
    assert X1.loc[0, "n_mid"] == 2
    assert X1.loc[0, "n_dist"] == 3
