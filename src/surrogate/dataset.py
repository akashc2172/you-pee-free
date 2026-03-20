"""
Schema-driven dataset assembly for surrogate training.

This is the only supported path for building (X, y) from a campaign results table.
It enforces:
- valid rows only
- Tier-1 transformed outputs only (no silent drift)
- explicit feature column selection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.surrogate.output_schema import (
    SCHEMA_V1,
    SurrogateOutputSchema,
    add_transformed_targets,
    coerce_required_raw_columns,
    tier1_target_columns,
)


@dataclass(frozen=True)
class TrainingAssembly:
    X: pd.DataFrame
    y: pd.DataFrame
    used_rows: pd.DataFrame
    x_columns: List[str]
    y_columns: List[str]


def filter_valid_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "run_status" not in df.columns:
        raise ValueError("results table missing required column: run_status")
    return df[df["run_status"] == "valid"].copy().reset_index(drop=True)


def assemble_training_data(
    results_df: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    include_optional_outputs: bool = False,
    schema: SurrogateOutputSchema = SCHEMA_V1,
) -> TrainingAssembly:
    """
    Build X and y for surrogate training using SCHEMA_V1.

    Preconditions:
    - `results_df` must include design-feature columns in `feature_columns`
    - `results_df` must include the raw Tier-1 metric columns (or known aliases)
    - `run_status` must be present
    """
    valid = filter_valid_rows(results_df)

    missing_x = [c for c in feature_columns if c not in valid.columns]
    if missing_x:
        raise ValueError(f"missing required feature columns for X: {missing_x}")

    normalized = coerce_required_raw_columns(valid, schema=schema)
    transformed = add_transformed_targets(normalized, schema=schema)

    y_cols = tier1_target_columns(include_optional=include_optional_outputs, schema=schema)
    # Note: X is returned as the requested feature columns; callers may further
    # resolve realized vs requested features (e.g., realized hole counts) after assembly.
    X = transformed[list(feature_columns)].copy()
    y = transformed[y_cols].copy()

    # Final sanity: no accidental leakage of non-target outputs
    if list(y.columns) != y_cols:
        raise RuntimeError("unexpected y column ordering drift")

    return TrainingAssembly(
        X=X,
        y=y,
        used_rows=transformed,
        x_columns=list(X.columns),
        y_columns=list(y.columns),
    )

