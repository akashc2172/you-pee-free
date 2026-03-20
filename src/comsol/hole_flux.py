"""
Metadata-driven shaft-hole flux target generation, CSV parsing, and plotting support.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def _normalize_key(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def load_hole_sidecar(path: Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    holes = payload.get("holes", [])
    if not isinstance(holes, list):
        raise ValueError("invalid_hole_sidecar: holes must be a list")
    return payload


def build_shaft_hole_flux_targets(sidecar_path: Path) -> pd.DataFrame:
    """Build ordered shaft-hole flux extraction targets from the metadata sidecar."""
    payload = load_hole_sidecar(sidecar_path)
    records: List[Dict[str, Any]] = []
    for hole in payload.get("holes", []):
        if hole.get("type") != "shaft":
            continue
        hole_id = str(hole["hole_id"])
        records.append(
            {
                "hole_id": hole_id,
                "region": hole["region"],
                "type": hole["type"],
                "axial_x_mm": float(hole["axial_x_mm"]),
                "axial_rank": int(hole["axial_rank"]),
                "center_x_mm": float(hole["center_mm"][0]),
                "center_y_mm": float(hole["center_mm"][1]),
                "center_z_mm": float(hole["center_mm"][2]),
                "normal_x": float(hole["normal"][0]),
                "normal_y": float(hole["normal"][1]),
                "normal_z": float(hole["normal"][2]),
                "mask_radius_mm": float(
                    hole.get("selection_cylinder_radius_mm", hole["radius_mm"])
                ),
                "cut_plane_name": f"CP_{hole_id}",
                "signed_dv_name": f"DV_hole_{hole_id}_signed",
                "abs_dv_name": f"DV_hole_{hole_id}_abs",
            }
        )
    df = pd.DataFrame(records).sort_values(["axial_rank", "hole_id"]).reset_index(drop=True)
    return df


def parse_shaft_hole_flux_csv(csv_path: Path) -> pd.DataFrame:
    """
    Parse COMSOL-exported per-hole flux outputs.

    Supported formats:
    - Tall: hole_id, signed_flux_m3s, abs_flux_m3s, optional p_ramp
    - Wide: columns named like DV_hole_shaft_mid_001_signed / _abs
    """
    df = pd.read_csv(csv_path, comment="%")
    if df.empty:
        raise ValueError("empty_shaft_hole_flux_csv")

    normalized_columns = {_normalize_key(str(column)): column for column in df.columns}
    tall_required = {"hole_id", "signed_flux_m3s", "abs_flux_m3s"}
    if tall_required.issubset(normalized_columns.keys()):
        renamed = {
            normalized_columns["hole_id"]: "hole_id",
            normalized_columns["signed_flux_m3s"]: "signed_flux_m3s",
            normalized_columns["abs_flux_m3s"]: "abs_flux_m3s",
        }
        if "p_ramp" in normalized_columns:
            renamed[normalized_columns["p_ramp"]] = "p_ramp"
        out = df.rename(columns=renamed)[list(renamed.values())].copy()
        if "p_ramp" not in out.columns:
            out["p_ramp"] = pd.NA
        return out

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        p_ramp = row[normalized_columns["p_ramp"]] if "p_ramp" in normalized_columns else pd.NA
        bucket: Dict[str, Dict[str, Any]] = {}
        for column in df.columns:
            norm = _normalize_key(str(column))
            match = re.match(r"(?:dv_)?hole_(shaft_[a-z]+_\d{3})_(signed|abs)$", norm)
            if not match:
                continue
            hole_id, flux_kind = match.groups()
            bucket.setdefault(hole_id, {"hole_id": hole_id, "p_ramp": p_ramp})
            if flux_kind == "signed":
                bucket[hole_id]["signed_flux_m3s"] = float(row[column])
            else:
                bucket[hole_id]["abs_flux_m3s"] = float(row[column])
        records.extend(bucket.values())

    if not records:
        raise ValueError("no_shaft_hole_flux_columns_found")

    out = pd.DataFrame(records)
    for required in ("signed_flux_m3s", "abs_flux_m3s"):
        if required not in out.columns:
            out[required] = pd.NA
    return out[["hole_id", "p_ramp", "signed_flux_m3s", "abs_flux_m3s"]]


def merge_flux_with_targets(sidecar_path: Path, flux_csv: Path) -> pd.DataFrame:
    targets = build_shaft_hole_flux_targets(sidecar_path)
    flux = parse_shaft_hole_flux_csv(flux_csv)
    merged = targets.merge(flux, on="hole_id", how="left")
    if "p_ramp" not in merged.columns:
        merged["p_ramp"] = pd.NA
    return merged.sort_values(["axial_rank", "hole_id"]).reset_index(drop=True)


def plot_shaft_hole_flux(merged: pd.DataFrame, output_dir: Path, stem: str) -> Dict[str, str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = merged.sort_values(["axial_rank", "hole_id"]).reset_index(drop=True)

    abs_png = output_dir / f"{stem}_abs_flux.png"
    signed_png = output_dir / f"{stem}_signed_flux.png"

    plt.figure(figsize=(8, 4.5))
    plt.plot(ordered["axial_x_mm"], ordered["abs_flux_m3s"], marker="o")
    plt.xlabel("axial_x_mm")
    plt.ylabel("abs_flux_m3s")
    plt.title("Shaft Hole Absolute Flux vs Axial Position")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(abs_png, dpi=200)
    plt.close()

    plt.figure(figsize=(8, 4.5))
    plt.plot(ordered["axial_x_mm"], ordered["signed_flux_m3s"], marker="o")
    plt.xlabel("axial_x_mm")
    plt.ylabel("signed_flux_m3s")
    plt.title("Shaft Hole Signed Flux vs Axial Position")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(signed_png, dpi=200)
    plt.close()

    return {
        "abs_flux_plot": str(abs_png),
        "signed_flux_plot": str(signed_png),
    }
