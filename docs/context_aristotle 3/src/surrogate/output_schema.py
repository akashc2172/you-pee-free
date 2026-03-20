"""
Surrogate output schema (single source of truth).

This module freezes:
- which outputs are eligible as Tier-1 surrogate targets,
- how transformed targets are derived (including clamping),
- which columns are QC-only (Tier-2) vs diagnostics (Tier-3).

Downstream code MUST import this file rather than re-listing columns ad-hoc.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd


DEFAULT_EPS = 1e-6


def _require_columns(df: pd.DataFrame, required: Iterable[str], context: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{context}: missing required columns: {missing}")


def clamp01(x: pd.Series, eps: float = DEFAULT_EPS) -> pd.Series:
    """Clamp to (0,1) open interval for logit stability."""
    return x.astype(float).clip(lower=eps, upper=1.0 - eps)


def log_safe(x: pd.Series, eps: float = DEFAULT_EPS) -> pd.Series:
    """Stable log for nonnegative quantities (expects x >= 0)."""
    return np.log(np.maximum(x.astype(float), eps))


def logit(p: pd.Series, eps: float = DEFAULT_EPS) -> pd.Series:
    p = clamp01(p, eps=eps)
    return np.log(p / (1.0 - p))


def atanh_safe(x: pd.Series, eps: float = DEFAULT_EPS) -> pd.Series:
    """Stable atanh for values in [-1,1]."""
    x = x.astype(float).clip(lower=-1.0 + eps, upper=1.0 - eps)
    return np.arctanh(x)


@dataclass(frozen=True)
class SurrogateOutputSchema:
    """
    Schema definition for training targets.

    Raw fields are expected to exist in a campaign results table after COMSOL postprocessing.
    Transformed fields are derived deterministically by `add_transformed_targets`.
    """

    eps: float = DEFAULT_EPS

    # ---- Tier-1 surrogate targets (RAW) ----
    raw_required: List[str] = (
        "deltaP_Pa",
        "Q_out_ml_min",
        "exchange_number",
        "hole_flux_centroid_norm",
        "hole_flux_iqs_norm",
    )

    # ---- Tier-1 optional (RAW) ----
    raw_optional: List[str] = (
        "hole_flux_dominance_ratio",
        "net_direction_index",
    )

    # ---- Tier-1 transformed targets ----
    transformed_required: List[str] = (
        "log_deltaP",
        "log_Q_out",
        "log_Ex",
        "logit_centroid_norm",
        "logit_IQS",
    )

    transformed_optional: List[str] = (
        "log_R_max",
        "atanh_NDI",
    )

    # ---- Tier-2 QC / gating columns (machine-enforced for filtering, not modeled) ----
    qc_columns: List[str] = (
        "run_status",
        "mass_balance_relerr",
        "solver_converged_flag",
        "mesh_ndof",
        "n_active_holes",
        "invariant_warnings",
        "invariants_passed",
    )

    # ---- Tier-3 diagnostics (explicitly NOT surrogate targets) ----
    # Kept here so docs/code can point to a “do not optimize” list.
    diagnostics_columns: List[str] = (
        "prox_hole_abs_flux_ml_min",
        "mid_hole_abs_flux_ml_min",
        "dist_hole_abs_flux_ml_min",
        "frac_prox_hole_abs",
        "frac_mid_hole_abs",
        "frac_dist_hole_abs",
        "CV_Qsh",
        "q_sh_prox",
        "q_sh_mid",
        "q_sh_dist",
    )


SCHEMA_V1 = SurrogateOutputSchema()


RAW_ALIASES: Dict[str, List[str]] = {
    # Map canonical raw names to legacy/common alternatives in results tables.
    "deltaP_Pa": ["deltaP_Pa", "delta_p", "delta_P", "delta_p_pa"],
    "Q_out_ml_min": ["Q_out_ml_min", "q_out", "Q_out", "Q_total"],
    "exchange_number": ["exchange_number", "Ex"],
    "hole_flux_centroid_norm": ["hole_flux_centroid_norm", "xbar_h_norm", "centroid_norm"],
    "hole_flux_iqs_norm": ["hole_flux_iqs_norm", "iqs_norm", "IQS_norm"],
    "hole_flux_dominance_ratio": ["hole_flux_dominance_ratio", "R_max", "hole_dominance_ratio"],
    "net_direction_index": ["net_direction_index", "NDI"],
}


def coerce_required_raw_columns(df: pd.DataFrame, schema: SurrogateOutputSchema = SCHEMA_V1) -> pd.DataFrame:
    """
    Ensure canonical raw Tier-1 columns exist by renaming from known aliases.
    Errors loudly if required fields cannot be found.
    """
    out = df.copy()
    for canonical in list(schema.raw_required) + list(schema.raw_optional):
        if canonical in out.columns:
            continue
        candidates = RAW_ALIASES.get(canonical, [])
        found = next((c for c in candidates if c in out.columns), None)
        if found is not None:
            out[canonical] = out[found]
    _require_columns(out, schema.raw_required, context="surrogate_schema_raw")
    return out


def add_transformed_targets(df: pd.DataFrame, schema: SurrogateOutputSchema = SCHEMA_V1) -> pd.DataFrame:
    """
    Add transformed Tier-1 targets to a results DataFrame.

    Preconditions:
    - canonical raw columns exist (use `coerce_required_raw_columns` first)
    """
    out = df.copy()
    eps = float(schema.eps)

    out["log_deltaP"] = log_safe(out["deltaP_Pa"].abs(), eps=eps)
    out["log_Q_out"] = log_safe(out["Q_out_ml_min"].abs(), eps=eps)
    out["log_Ex"] = log_safe(out["exchange_number"].abs(), eps=eps)
    out["logit_centroid_norm"] = logit(out["hole_flux_centroid_norm"], eps=eps)
    out["logit_IQS"] = logit(out["hole_flux_iqs_norm"], eps=eps)

    if "hole_flux_dominance_ratio" in out.columns:
        out["log_R_max"] = log_safe(out["hole_flux_dominance_ratio"], eps=eps)
    if "net_direction_index" in out.columns:
        out["atanh_NDI"] = atanh_safe(out["net_direction_index"], eps=eps)

    _require_columns(out, schema.transformed_required, context="surrogate_schema_transformed")
    return out


def tier1_target_columns(include_optional: bool = False, schema: SurrogateOutputSchema = SCHEMA_V1) -> List[str]:
    cols = list(schema.transformed_required)
    if include_optional:
        cols.extend(schema.transformed_optional)
    return cols

