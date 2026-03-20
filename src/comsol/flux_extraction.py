"""Postprocessing helpers for metadata-driven COMSOL flux extraction outputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import math
import numpy as np
import pandas as pd

DEFAULT_ACTIVE_EPS_ML_MIN = 1e-6
INVARIANT_TOL = 1e-9


@dataclass
class FluxExtractionArtifacts:
    design_id: str
    scalars_csv: Path
    features_csv: Path


def _finite_or_nan(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return parsed if math.isfinite(parsed) else float("nan")


def _gini(values: List[float]) -> float:
    filtered = [float(value) for value in values if math.isfinite(float(value)) and float(value) >= 0.0]
    if not filtered:
        return float("nan")
    mean_value = sum(filtered) / len(filtered)
    if mean_value <= 0.0:
        return float("nan")
    diffs = 0.0
    for left in filtered:
        for right in filtered:
            diffs += abs(left - right)
    return diffs / (2.0 * len(filtered) * len(filtered) * mean_value)


def _weighted_centroid(values: pd.Series, positions: pd.Series) -> float:
    weights = values.astype(float)
    coords = positions.astype(float)
    total = float(weights.sum())
    if total <= 0.0:
        return float("nan")
    return float((weights * coords).sum() / total)


def _weighted_spread(values: pd.Series, positions: pd.Series, centroid: float) -> float:
    weights = values.astype(float)
    coords = positions.astype(float)
    total = float(weights.sum())
    if total <= 0.0 or not math.isfinite(centroid):
        return float("nan")
    variance = float((weights * (coords - centroid) ** 2).sum() / total)
    return math.sqrt(max(variance, 0.0))


def _flux_iqs_norm(
    abs_flux: pd.Series,
    axial_x_mm: pd.Series,
    stent_length_mm: float,
) -> float:
    """
    Flux interquartile span (IQS), normalized by stent length.

    IQS = (x_75 - x_25) / L where x_q are flux-weighted CDF quantiles along the axis.
    Uses absolute flux weights; requires L > 0 and at least one positive-weight hole.
    """
    if not math.isfinite(stent_length_mm) or stent_length_mm <= 0.0:
        return float("nan")

    w = pd.to_numeric(abs_flux, errors="coerce").astype(float)
    x = pd.to_numeric(axial_x_mm, errors="coerce").astype(float)
    mask = w.notna() & x.notna() & (w > 0.0)
    if not bool(mask.any()):
        return float("nan")

    w = w[mask]
    x = x[mask]
    order = x.argsort(kind="mergesort")
    x_sorted = x.iloc[order].to_numpy(dtype=float)
    w_sorted = w.iloc[order].to_numpy(dtype=float)

    total = float(w_sorted.sum())
    if not math.isfinite(total) or total <= 0.0:
        return float("nan")

    cdf = np.cumsum(w_sorted) / total

    def _quantile(q: float) -> float:
        idx = int(np.searchsorted(cdf, q, side="left"))
        idx = max(0, min(idx, len(cdf) - 1))
        if idx == 0:
            return float(x_sorted[0])
        x0 = float(x_sorted[idx - 1])
        x1 = float(x_sorted[idx])
        c0 = float(cdf[idx - 1])
        c1 = float(cdf[idx])
        if not (math.isfinite(c0) and math.isfinite(c1)) or c1 <= c0:
            return float(x1)
        t = (q - c0) / (c1 - c0)
        return x0 + t * (x1 - x0)

    x25 = _quantile(0.25)
    x75 = _quantile(0.75)
    span = max(0.0, float(x75 - x25))
    return float(span / float(stent_length_mm))


def load_flux_scalars_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="%")
    if df.empty:
        raise ValueError(f"empty_flux_scalars_csv: {path}")
    return df


def load_flux_features_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, comment="%")
    if df.empty:
        raise ValueError(f"empty_flux_features_csv: {path}")
    return df


def summarize_flux_outputs(
    design_id: str,
    scalars_df: pd.DataFrame,
    features_df: pd.DataFrame,
    active_eps_ml_min: float = DEFAULT_ACTIVE_EPS_ML_MIN,
) -> pd.DataFrame:
    """Build one-row-per-snapshot summary rows from COMSOL feature exports."""
    rows: List[Dict[str, Any]] = []

    if "p_ramp" not in scalars_df.columns:
        scalars_df = scalars_df.copy()
        scalars_df["p_ramp"] = pd.NA
    if "p_ramp" not in features_df.columns:
        features_df = features_df.copy()
        features_df["p_ramp"] = pd.NA

    raw_p_ramps = list(scalars_df["p_ramp"].tolist()) + list(features_df["p_ramp"].tolist())
    all_p_ramps: List[Any] = []
    seen_non_null = set()
    saw_null = False
    for value in raw_p_ramps:
        if pd.isna(value):
            saw_null = True
            continue
        key = str(value)
        if key not in seen_non_null:
            seen_non_null.add(key)
            all_p_ramps.append(value)
    all_p_ramps.sort()
    if saw_null or not all_p_ramps:
        all_p_ramps = [pd.NA] + all_p_ramps

    for p_ramp in all_p_ramps:
        scalar_rows = scalars_df[scalars_df["p_ramp"].isna()] if pd.isna(p_ramp) else scalars_df[scalars_df["p_ramp"] == p_ramp]
        feature_rows = features_df[features_df["p_ramp"].isna()] if pd.isna(p_ramp) else features_df[features_df["p_ramp"] == p_ramp]

        scalar_row = scalar_rows.iloc[-1].to_dict() if not scalar_rows.empty else {}
        feature_rows = feature_rows.copy()

        summary: Dict[str, Any] = {
            "design_id": design_id,
            "p_ramp": p_ramp,
            "Q_out_ml_min": float(scalar_row.get("Q_out_ml_min", scalar_row.get("q_out_ml_min", float("nan")))),
            "Q_in_ml_min": float(scalar_row.get("Q_in_ml_min", scalar_row.get("q_in_ml_min", float("nan")))),
            "Q_lumen_out_ml_min": float(scalar_row.get("Q_lumen_out_ml_min", float("nan"))),
            "Q_annulus_out_ml_min": float(scalar_row.get("Q_annulus_out_ml_min", float("nan"))),
            "p_in_avg_Pa": float(scalar_row.get("p_in_avg_Pa", float("nan"))),
            "p_out_avg_Pa": float(scalar_row.get("p_out_avg_Pa", float("nan"))),
            "max_vel_m_s": float(scalar_row.get("max_vel_m_s", float("nan"))),
            "max_p_Pa": float(scalar_row.get("max_p_Pa", float("nan"))),
            "min_p_Pa": float(scalar_row.get("min_p_Pa", float("nan"))),
            "mesh_ndof": scalar_row.get("mesh_ndof", pd.NA),
            "solver_converged_flag": scalar_row.get("solver_converged_flag", pd.NA),
            "solver_message": scalar_row.get("solver_message", ""),
        }
        invariant_warnings: List[str] = []
        hard_invariant_failures: List[str] = []

        p_in = summary["p_in_avg_Pa"]
        p_out = summary["p_out_avg_Pa"]
        q_out = summary["Q_out_ml_min"]

        if math.isfinite(p_in) and math.isfinite(p_out):
            summary["deltaP_Pa"] = p_in - p_out
        else:
            summary["deltaP_Pa"] = float("nan")

        if math.isfinite(q_out) and math.isfinite(summary["deltaP_Pa"]) and abs(summary["deltaP_Pa"]) > 1e-15:
            summary["conductance_ml_min_per_Pa"] = q_out / summary["deltaP_Pa"]
        else:
            summary["conductance_ml_min_per_Pa"] = float("nan")

        if math.isfinite(q_out) and abs(q_out) > 1e-15:
            summary["frac_lumen_out"] = summary["Q_lumen_out_ml_min"] / q_out
            summary["frac_annulus_out"] = summary["Q_annulus_out_ml_min"] / q_out
        else:
            summary["frac_lumen_out"] = float("nan")
            summary["frac_annulus_out"] = float("nan")

        if "feature_id" in feature_rows.columns and feature_rows["feature_id"].duplicated().any():
            hard_invariant_failures.append("duplicate_feature_ids")

        holes = feature_rows[feature_rows["feature_class"] == "hole_cap"].copy()
        unroof = feature_rows[feature_rows["feature_class"] == "unroof_patch"].copy()

        hole_abs = pd.to_numeric(holes.get("abs_flux_ml_min"), errors="coerce").fillna(0.0).astype(float)
        hole_signed = pd.to_numeric(holes.get("signed_flux_ml_min"), errors="coerce").fillna(0.0).astype(float)
        unroof_abs = pd.to_numeric(unroof.get("abs_flux_ml_min"), errors="coerce").fillna(0.0).astype(float)
        unroof_signed = pd.to_numeric(unroof.get("signed_flux_ml_min"), errors="coerce").fillna(0.0).astype(float)

        if not hole_abs.empty and bool((hole_abs < -INVARIANT_TOL).any()):
            hard_invariant_failures.append("negative_hole_abs_flux")
        if not hole_abs.empty and bool(((hole_abs + INVARIANT_TOL) < hole_signed.abs()).any()):
            hard_invariant_failures.append("hole_abs_lt_signed_magnitude")
        if not unroof_abs.empty and bool((unroof_abs < -INVARIANT_TOL).any()):
            hard_invariant_failures.append("negative_unroof_abs_flux")
        if not unroof_abs.empty and bool(((unroof_abs + INVARIANT_TOL) < unroof_signed.abs()).any()):
            hard_invariant_failures.append("unroof_abs_lt_signed_magnitude")

        summary["Q_holes_net_ml_min"] = float(hole_signed.sum())
        summary["Q_holes_abs_ml_min"] = float(hole_abs.sum())

        active = hole_abs > active_eps_ml_min
        summary["n_active_holes"] = int(active.sum())
        if int(active.sum()) > 0:
            active_abs = hole_abs[active]
            mean_abs = float(active_abs.mean())
            summary["hole_uniformity_cv"] = (
                float(active_abs.std(ddof=0)) / mean_abs if mean_abs > 0.0 else float("nan")
            )
            summary["hole_uniformity_gini"] = _gini(active_abs.tolist())
            summary["hole_flux_dominance_ratio"] = (
                float(active_abs.max()) / mean_abs if mean_abs > 0.0 else float("nan")
            )
        else:
            summary["hole_uniformity_cv"] = float("nan")
            summary["hole_uniformity_gini"] = float("nan")
            summary["hole_flux_dominance_ratio"] = float("nan")

        for zone in ("prox", "mid", "dist"):
            zone_abs = holes.loc[holes["zone"] == zone, "abs_flux_ml_min"].fillna(0.0).astype(float).sum()
            summary[f"{zone}_hole_abs_flux_ml_min"] = float(zone_abs)

        if summary["Q_holes_abs_ml_min"] > 1e-15:
            summary["frac_prox_hole_abs"] = summary["prox_hole_abs_flux_ml_min"] / summary["Q_holes_abs_ml_min"]
            summary["frac_mid_hole_abs"] = summary["mid_hole_abs_flux_ml_min"] / summary["Q_holes_abs_ml_min"]
            summary["frac_dist_hole_abs"] = summary["dist_hole_abs_flux_ml_min"] / summary["Q_holes_abs_ml_min"]
        else:
            summary["frac_prox_hole_abs"] = float("nan")
            summary["frac_mid_hole_abs"] = float("nan")
            summary["frac_dist_hole_abs"] = float("nan")

        summary["Q_unroof_net_ml_min"] = float(unroof_signed.sum())
        summary["Q_unroof_abs_ml_min"] = float(unroof_abs.sum())
        total_unroof_length = (
            float(pd.to_numeric(unroof["open_length_mm"], errors="coerce").fillna(0.0).astype(float).sum())
            if "open_length_mm" in unroof.columns
            else 0.0
        )
        summary["frac_unroof_of_total"] = (
            summary["Q_unroof_abs_ml_min"] / q_out if math.isfinite(q_out) and abs(q_out) > 1e-15 else float("nan")
        )
        summary["frac_unroof_of_outlet_flow"] = summary["frac_unroof_of_total"]
        summary["unroof_flux_density_ml_min_per_mm"] = (
            summary["Q_unroof_abs_ml_min"] / total_unroof_length if total_unroof_length > 1e-15 else float("nan")
        )
        summary["unroof_vs_holes_ratio"] = (
            summary["Q_unroof_abs_ml_min"] / summary["Q_holes_abs_ml_min"]
            if summary["Q_holes_abs_ml_min"] > 1e-15
            else float("nan")
        )

        summary["Q_exchange_total_abs_ml_min"] = summary["Q_holes_abs_ml_min"] + summary["Q_unroof_abs_ml_min"]
        summary["frac_unroof_of_exchange_total"] = (
            summary["Q_unroof_abs_ml_min"] / summary["Q_exchange_total_abs_ml_min"]
            if summary["Q_exchange_total_abs_ml_min"] > 1e-15
            else float("nan")
        )
        summary["exchange_number"] = (
            summary["Q_exchange_total_abs_ml_min"] / q_out
            if math.isfinite(q_out) and abs(q_out) > 1e-15
            else float("nan")
        )
        summary["hole_only_exchange_number"] = (
            summary["Q_holes_abs_ml_min"] / q_out
            if math.isfinite(q_out) and abs(q_out) > 1e-15
            else float("nan")
        )
        summary["net_direction_index"] = (
            summary["Q_holes_net_ml_min"] / summary["Q_holes_abs_ml_min"]
            if summary["Q_holes_abs_ml_min"] > 1e-15
            else float("nan")
        )

        if math.isfinite(summary["Q_in_ml_min"]) and math.isfinite(summary["Q_out_ml_min"]):
            denom = max(abs(summary["Q_in_ml_min"]), abs(summary["Q_out_ml_min"]), 1e-15)
            summary["mass_balance_relerr"] = abs(summary["Q_in_ml_min"] + summary["Q_out_ml_min"]) / denom
        else:
            summary["mass_balance_relerr"] = float("nan")

        if summary["Q_holes_abs_ml_min"] + INVARIANT_TOL < abs(summary["Q_holes_net_ml_min"]):
            hard_invariant_failures.append("holes_abs_lt_net_magnitude")
        if summary["Q_exchange_total_abs_ml_min"] + INVARIANT_TOL < abs(
            summary["Q_holes_net_ml_min"] + summary["Q_unroof_net_ml_min"]
        ):
            hard_invariant_failures.append("exchange_abs_lt_net_magnitude")
        if math.isfinite(summary["frac_lumen_out"]) and math.isfinite(summary["frac_annulus_out"]):
            if abs((summary["frac_lumen_out"] + summary["frac_annulus_out"]) - 1.0) > 1e-6:
                invariant_warnings.append("distal_partition_fractions_do_not_sum_to_one")
        if math.isfinite(summary["frac_prox_hole_abs"]) and math.isfinite(summary["frac_mid_hole_abs"]) and math.isfinite(summary["frac_dist_hole_abs"]):
            if abs(
                (
                    summary["frac_prox_hole_abs"]
                    + summary["frac_mid_hole_abs"]
                    + summary["frac_dist_hole_abs"]
                )
                - 1.0
            ) > 1e-6:
                hard_invariant_failures.append("hole_zone_fractions_do_not_sum_to_one")

        active_holes = holes.loc[hole_abs > active_eps_ml_min].copy()
        if not active_holes.empty and "axial_x_mm" in active_holes.columns:
            active_positions = pd.to_numeric(active_holes["axial_x_mm"], errors="coerce")
            active_abs = pd.to_numeric(active_holes["abs_flux_ml_min"], errors="coerce").fillna(0.0)
            valid_position_mask = active_positions.notna()
            if bool(valid_position_mask.any()):
                centroid = _weighted_centroid(active_abs[valid_position_mask], active_positions[valid_position_mask])
                summary["hole_flux_centroid_x_mm"] = centroid
                summary["hole_flux_spread_x_mm"] = _weighted_spread(
                    active_abs[valid_position_mask],
                    active_positions[valid_position_mask],
                    centroid,
                )
                stent_length_mm = _finite_or_nan(
                    scalar_row.get("stent_length_mm", scalar_row.get("stent_length", float("nan")))
                )
                if not math.isfinite(stent_length_mm) or stent_length_mm <= 0.0:
                    invariant_warnings.append("missing_stent_length_for_normalization")
                    summary["hole_flux_centroid_norm"] = float("nan")
                    summary["hole_flux_spread_norm"] = float("nan")
                    summary["hole_flux_iqs_norm"] = float("nan")
                else:
                    summary["hole_flux_centroid_norm"] = (
                        float(centroid / stent_length_mm) if math.isfinite(centroid) else float("nan")
                    )
                    spread = summary["hole_flux_spread_x_mm"]
                    summary["hole_flux_spread_norm"] = (
                        float(spread / stent_length_mm) if math.isfinite(spread) else float("nan")
                    )
                    summary["hole_flux_iqs_norm"] = _flux_iqs_norm(
                        abs_flux=active_abs[valid_position_mask],
                        axial_x_mm=active_positions[valid_position_mask],
                        stent_length_mm=stent_length_mm,
                    )
            else:
                summary["hole_flux_centroid_x_mm"] = float("nan")
                summary["hole_flux_spread_x_mm"] = float("nan")
                summary["hole_flux_centroid_norm"] = float("nan")
                summary["hole_flux_spread_norm"] = float("nan")
                summary["hole_flux_iqs_norm"] = float("nan")
        else:
            summary["hole_flux_centroid_x_mm"] = float("nan")
            summary["hole_flux_spread_x_mm"] = float("nan")
            summary["hole_flux_centroid_norm"] = float("nan")
            summary["hole_flux_spread_norm"] = float("nan")
            summary["hole_flux_iqs_norm"] = float("nan")

        if not holes.empty and bool((hole_signed < 0.0).sum() > (len(hole_signed) / 2.0)):
            invariant_warnings.append("hole_flux_majority_negative")

        for _, hole in holes.iterrows():
            hole_key = str(hole.get("parent_feature") or hole.get("feature_id"))
            abs_val = _finite_or_nan(hole.get("abs_flux_ml_min", 0.0))
            signed_val = _finite_or_nan(hole.get("signed_flux_ml_min", 0.0))
            summary[f"Q_hole_{hole_key}_ml_min"] = signed_val
            summary[f"absQ_hole_{hole_key}_ml_min"] = abs_val
            summary[f"hole_active_{hole_key}"] = int(math.isfinite(abs_val) and abs_val > active_eps_ml_min)

        all_warnings = sorted(dict.fromkeys(list(hard_invariant_failures) + list(invariant_warnings)))
        summary["invariant_warnings"] = ";".join(all_warnings)
        # `invariants_passed` is meant to capture hard contract violations, not
        # every informational warning. This prevents innocuous warnings (e.g.
        # missing normalization length) from failing tests/QC gates.
        summary["invariants_passed"] = int(len(dict.fromkeys(hard_invariant_failures)) == 0)

        rows.append(summary)

    return pd.DataFrame(rows)
