#!/usr/bin/env python3
"""Generate multiple visualization concepts for stent hole flux data.

Creates 5 distinct figure concepts from COMSOL per-hole flux CSV data,
optionally enriched with 3D coordinates from the .holes.json sidecar.

Usage:
    python scripts/visualize_hole_flux_concepts.py path/to/design_0000_shaft_hole_flux.csv
    python scripts/visualize_hole_flux_concepts.py flux.csv --sidecar design.holes.json
    python scripts/visualize_hole_flux_concepts.py --demo  # uses embedded test data
"""

from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.collections import LineCollection
from matplotlib import patheffects
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
REGION_COLORS = {"prox": "#3b82f6", "mid": "#10b981", "dist": "#ef4444"}
REGION_COLORS_LIGHT = {"prox": "#dbeafe", "mid": "#d1fae5", "dist": "#fee2e2"}
REGION_LABELS = {"prox": "Proximal", "mid": "Middle", "dist": "Distal"}
REGION_ORDER = {"prox": 0, "mid": 1, "dist": 2}

TUBE_BODY_COLOR = "#cbd5e1"
TUBE_EDGE_COLOR = "#64748b"
PIGTAIL_COLOR = "#94a3b8"

COIL_R = 6.0
COIL_PITCH = 6.0
COIL_TURNS = 1.5
PIGTAIL_HEIGHT = COIL_PITCH * COIL_TURNS

DEMO_CSV = """\
hole_id,axial_x_mm,region,type,p_ramp,signed_flux_m3s,abs_flux_m3s
shaft_prox_000,1.0,prox,shaft,,-3.77e-12,1.89e-11
shaft_prox_001,4.6,prox,shaft,,9.20e-12,1.96e-11
shaft_prox_002,8.2,prox,shaft,,-8.48e-12,1.89e-11
shaft_prox_003,11.8,prox,shaft,,-1.41e-11,2.16e-11
shaft_prox_004,15.4,prox,shaft,,3.20e-12,2.13e-11
shaft_prox_005,19.0,prox,shaft,,-3.35e-12,3.11e-11
shaft_prox_006,22.6,prox,shaft,,-4.24e-12,1.22e-11
shaft_mid_000,24.6,mid,shaft,,-6.57e-12,2.57e-11
shaft_mid_001,105.0,mid,shaft,,9.69e-12,1.29e-11
shaft_mid_002,185.0,mid,shaft,,2.10e-12,9.97e-12
shaft_dist_000,187.0,dist,shaft,,1.24e-12,4.63e-12
shaft_dist_001,206.0,dist,shaft,,-1.26e-11,2.79e-11
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_flux_csv(path: Optional[Path]) -> pd.DataFrame:
    if path is None:
        df = pd.read_csv(io.StringIO(DEMO_CSV))
    else:
        df = pd.read_csv(path)
    df.columns = df.columns.str.strip()

    renames: Dict[str, str] = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "_")
        if "signed" in cl and "flux" in cl:
            renames[c] = "signed_flux"
        elif "abs" in cl and "flux" in cl:
            renames[c] = "abs_flux"
    df.rename(columns=renames, inplace=True)

    # Handle multiple solution steps (e.g. p_ramp sweep)
    # Generic visualizations usually want the FINAL step.
    if "p_ramp" in df.columns and df["p_ramp"].nunique() > 1:
        latest_ramp = df["p_ramp"].max()
        df = df[df["p_ramp"] == latest_ramp].copy()

    df["_rr"] = df["region"].map(REGION_ORDER).fillna(99).astype(int)
    # Extract numeric suffix from hole_id (e.g. shaft_prox_001 -> 1)
    df["_suf"] = df["hole_id"].str.extract(r"(\d+)$").fillna(0).astype(int)
    df = df.sort_values(["_rr", "_suf"]).reset_index(drop=True)
    df.drop(columns=["_rr", "_suf"], inplace=True)
    return df


def load_sidecar(path: Optional[Path]) -> Optional[dict]:
    if path and path.exists():
        return json.loads(path.read_text())
    return None


def infer_stent_length(df: pd.DataFrame, sidecar: Optional[dict]) -> float:
    if sidecar and "stent_length_mm" in sidecar:
        return sidecar["stent_length_mm"]
    return float(df["axial_x_mm"].max() * 1.05)


def infer_r_outer(sidecar: Optional[dict]) -> float:
    if sidecar and "r_outer_mm" in sidecar:
        return sidecar["r_outer_mm"]
    return 1.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def pigtail_xy(start_x: float, direction: str, n: int = 300):
    t = np.linspace(0, 1, n)
    sign = -1.0 if direction == "left" else 1.0
    x = start_x + sign * PIGTAIL_HEIGHT * t
    y = COIL_R * np.sin(2 * np.pi * COIL_TURNS * t)
    return x, y


def pigtail_xyz(start_x: float, direction: str, n: int = 300):
    t = np.linspace(0, 1, n)
    sign = -1.0 if direction == "left" else 1.0
    x = start_x + sign * PIGTAIL_HEIGHT * t
    y = COIL_R * np.cos(2 * np.pi * COIL_TURNS * t)
    z = COIL_R * np.sin(2 * np.pi * COIL_TURNS * t)
    return x, y, z


def tube_surface_3d(x_start: float, x_end: float, r: float,
                    nx: int = 60, ntheta: int = 30):
    x = np.linspace(x_start, x_end, nx)
    theta = np.linspace(0, 2 * np.pi, ntheta)
    X, T = np.meshgrid(x, theta)
    Y = r * np.cos(T)
    Z = r * np.sin(T)
    return X, Y, Z


def section_boundaries(df: pd.DataFrame) -> List[float]:
    """Compute x-boundaries between adjacent regions for vertical dividers."""
    bounds = []
    regions_in_order = (
        df.groupby("region")["axial_x_mm"]
        .agg(["min", "max"])
        .reindex(["prox", "mid", "dist"])
        .dropna()
    )
    prev_max = None
    for region, row in regions_in_order.iterrows():
        if prev_max is not None:
            bounds.append((prev_max + row["min"]) / 2)
        prev_max = row["max"]
    return bounds


def region_spans(df: pd.DataFrame) -> Dict[str, Tuple[float, float]]:
    """Get (min_x, max_x) for each region."""
    return {
        region: (grp["axial_x_mm"].min(), grp["axial_x_mm"].max())
        for region, grp in df.groupby("region")
    }


# ---------------------------------------------------------------------------
# CONCEPT 1 — Anatomical Flux Profile
#   Stent silhouette below, signed flux stems above, physical x-axis
# ---------------------------------------------------------------------------

def concept_1(df: pd.DataFrame, stent_length: float, r_outer: float,
              out: Path) -> None:
    fig = plt.figure(figsize=(14, 6.5), facecolor="white")
    gs = gridspec.GridSpec(2, 1, height_ratios=[3.5, 1], hspace=0.08)
    ax_flux = fig.add_subplot(gs[0])
    ax_stent = fig.add_subplot(gs[1], sharex=ax_flux)

    # --- Flux stems ---
    for _, row in df.iterrows():
        c = REGION_COLORS[row["region"]]
        ax_flux.plot(
            [row["axial_x_mm"]] * 2, [0, row["signed_flux"]],
            color=c, linewidth=2.2, solid_capstyle="round", zorder=3,
        )
        ax_flux.plot(
            row["axial_x_mm"], row["signed_flux"], "o",
            color=c, markersize=9, markeredgecolor="white",
            markeredgewidth=1.0, zorder=4,
        )

    ax_flux.axhline(0, color="#334155", linewidth=0.7, alpha=0.5)

    for bx in section_boundaries(df):
        ax_flux.axvline(bx, color="#e2e8f0", linewidth=1.2, linestyle="--")

    spans = region_spans(df)
    ylim = ax_flux.get_ylim()
    for region in ["prox", "mid", "dist"]:
        if region not in spans:
            continue
        lo, hi = spans[region]
        ax_flux.axvspan(lo - 2, hi + 2, color=REGION_COLORS_LIGHT[region], alpha=0.35, zorder=0)
        ax_flux.text(
            (lo + hi) / 2, ylim[1] * 0.92, REGION_LABELS[region],
            ha="center", va="top", fontsize=10, fontweight="bold",
            color=REGION_COLORS[region], alpha=0.85,
        )

    ax_flux.set_ylabel("Signed Flux  [m³/s]", fontsize=11)
    ax_flux.set_title(
        "Concept 1 — Anatomical Flux Profile\n"
        "Physical axial position · stent schematic below",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax_flux.grid(axis="y", alpha=0.15)
    ax_flux.tick_params(labelbottom=False)
    handles = [mpatches.Patch(color=REGION_COLORS[r], label=REGION_LABELS[r])
               for r in ("prox", "mid", "dist") if r in spans]
    ax_flux.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.9)

    # --- Stent schematic ---
    body = mpatches.FancyBboxPatch(
        (0, -0.4), stent_length, 0.8,
        boxstyle=mpatches.BoxStyle.Round(pad=0.15),
        facecolor=TUBE_BODY_COLOR, edgecolor=TUBE_EDGE_COLOR,
        linewidth=1.2, zorder=2,
    )
    ax_stent.add_patch(body)

    px, py = pigtail_xy(0, "left")
    ax_stent.plot(px, py * 0.15, color=PIGTAIL_COLOR, linewidth=2.0, alpha=0.55, zorder=1)
    dx, dy = pigtail_xy(stent_length, "right")
    ax_stent.plot(dx, dy * 0.15, color=PIGTAIL_COLOR, linewidth=2.0, alpha=0.55, zorder=1)

    for _, row in df.iterrows():
        marker = "D" if row["type"] == "coil" else "o"
        ax_stent.plot(
            row["axial_x_mm"], 0, marker, color=REGION_COLORS[row["region"]],
            markersize=6, markeredgecolor="white", markeredgewidth=0.6, zorder=5,
        )

    ax_stent.set_xlim(-PIGTAIL_HEIGHT - 3, stent_length + PIGTAIL_HEIGHT + 3)
    ax_stent.set_ylim(-1.5, 1.5)
    ax_stent.set_xlabel("Axial Position  [mm]", fontsize=11)
    ax_stent.set_yticks([])
    ax_stent.spines["left"].set_visible(False)
    ax_stent.text(
        stent_length / 2, -1.2, "stent body (side view, not to scale)",
        ha="center", va="top", fontsize=8, color="#94a3b8", style="italic",
    )

    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Concept 1 → {out}")


# ---------------------------------------------------------------------------
# CONCEPT 2 — Categorical Lollipop
#   Evenly-spaced hole IDs, dual signed/abs markers, region bands
# ---------------------------------------------------------------------------

def concept_2(df: pd.DataFrame, out: Path) -> None:
    fig, (ax_s, ax_a) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, facecolor="white")

    hole_ids = df["hole_id"].tolist()
    xs = np.arange(len(hole_ids))

    # Region background bands
    prev_region = None
    band_start = 0
    for ax in (ax_s, ax_a):
        prev_region = None
        band_start = 0
        for i, hid in enumerate(hole_ids):
            region = df.loc[df["hole_id"] == hid, "region"].values[0]
            if region != prev_region and prev_region is not None:
                ax.axvspan(band_start - 0.5, i - 0.5,
                           color=REGION_COLORS_LIGHT[prev_region], alpha=0.4, zorder=0)
                band_start = i
            prev_region = region
        ax.axvspan(band_start - 0.5, len(hole_ids) - 0.5,
                   color=REGION_COLORS_LIGHT[prev_region], alpha=0.4, zorder=0)

    # Signed flux (top panel)
    for i, (_, row) in enumerate(df.iterrows()):
        c = REGION_COLORS[row["region"]]
        ax_s.plot([i, i], [0, row["signed_flux"]], color=c, linewidth=2, zorder=3)
        ax_s.plot(i, row["signed_flux"], "o", color=c, markersize=9,
                  markeredgecolor="white", markeredgewidth=0.8, zorder=4)

    ax_s.axhline(0, color="#334155", linewidth=0.6)
    ax_s.set_ylabel("Signed Flux  [m³/s]", fontsize=11)
    ax_s.set_title(
        "Concept 2 — Categorical Lollipop Chart\n"
        "Evenly-spaced holes · region color bands",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax_s.grid(axis="y", alpha=0.15)

    # Absolute flux (bottom panel)
    for i, (_, row) in enumerate(df.iterrows()):
        c = REGION_COLORS[row["region"]]
        ax_a.bar(i, row["abs_flux"], width=0.6, color=c, edgecolor="white",
                 linewidth=0.5, alpha=0.85, zorder=3)

    ax_a.set_ylabel("Absolute Flux  [m³/s]", fontsize=11)
    ax_a.set_xticks(xs)
    ax_a.set_xticklabels(hole_ids, rotation=50, ha="right", fontsize=8)
    ax_a.set_xlabel("Side Hole ID", fontsize=11)
    ax_a.grid(axis="y", alpha=0.15)

    handles = [mpatches.Patch(color=REGION_COLORS[r], label=REGION_LABELS[r])
               for r in ("prox", "mid", "dist")]
    ax_a.legend(handles=handles, loc="upper right", fontsize=9, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Concept 2 → {out}")


# ---------------------------------------------------------------------------
# CONCEPT 3 — 3D Flux Tube
#   3D stent wireframe + pigtails with colored/sized flux spheres
# ---------------------------------------------------------------------------

def concept_3(df: pd.DataFrame, stent_length: float, r_outer: float,
              sidecar: Optional[dict], out: Path) -> None:
    fig = plt.figure(figsize=(14, 8), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")

    tube_r_vis = r_outer * 3  # exaggerate tube radius for visibility

    # Body wireframe (axial lines + rings)
    n_ax = 8
    theta_ax = np.linspace(0, 2 * np.pi, n_ax, endpoint=False)
    body_x = np.linspace(0, stent_length, 80)
    for th in theta_ax:
        ax.plot(body_x, tube_r_vis * np.cos(th) * np.ones_like(body_x),
                tube_r_vis * np.sin(th) * np.ones_like(body_x),
                color=TUBE_BODY_COLOR, linewidth=0.5, alpha=0.4)

    ring_xs = np.linspace(0, stent_length, 12)
    th_ring = np.linspace(0, 2 * np.pi, 60)
    for rx in ring_xs:
        ax.plot(np.full_like(th_ring, rx),
                tube_r_vis * np.cos(th_ring),
                tube_r_vis * np.sin(th_ring),
                color=TUBE_BODY_COLOR, linewidth=0.4, alpha=0.3)

    # Pigtails
    for start_x, d in [(0, "left"), (stent_length, "right")]:
        hx, hy, hz = pigtail_xyz(start_x, d)
        ax.plot(hx, hy, hz, color=PIGTAIL_COLOR, linewidth=1.8, alpha=0.5)

    # Flux spheres at hole positions
    abs_vals = df["abs_flux"].values
    max_abs = abs_vals.max() if abs_vals.max() > 0 else 1.0
    sizes = 80 + 400 * (abs_vals / max_abs)

    signed = df["signed_flux"].values
    s_max = max(abs(signed.min()), abs(signed.max())) if len(signed) > 0 else 1.0
    norm_signed = signed / s_max

    cmap = plt.cm.RdBu_r
    colors = cmap(0.5 + 0.5 * norm_signed)

    # Use sidecar 3D coords if available, otherwise place on tube surface
    if sidecar:
        hole_map = {h["hole_id"]: h for h in sidecar.get("holes", [])}
    else:
        hole_map = {}

    for i, (_, row) in enumerate(df.iterrows()):
        h = hole_map.get(row["hole_id"])
        if h and "center_mm" in h:
            cx, cy, cz = h["center_mm"]
            # Push outward slightly for visibility
            dist = math.sqrt(cy**2 + cz**2)
            if dist > 0.01:
                scale = (tube_r_vis * 1.2) / max(dist, 0.01)
                cy *= scale
                cz *= scale
        else:
            arc = (i % 2) * 90.0
            rad = math.radians(arc)
            cx = row["axial_x_mm"]
            cy = tube_r_vis * 1.2 * math.cos(rad)
            cz = tube_r_vis * 1.2 * math.sin(rad)

        ax.scatter([cx], [cy], [cz], s=sizes[i], c=[colors[i]],
                   edgecolors="white", linewidths=0.6, alpha=0.9, zorder=5)
        ax.text(cx, cy, cz + tube_r_vis * 0.6,
                row["hole_id"].replace("shaft_", ""),
                fontsize=6, ha="center", color="#475569", alpha=0.7)

    ax.set_xlabel("X (axial) [mm]", fontsize=9, labelpad=8)
    ax.set_ylabel("Y [mm]", fontsize=9, labelpad=8)
    ax.set_zlabel("Z [mm]", fontsize=9, labelpad=8)
    ax.set_title(
        "Concept 3 — 3D Flux Tube\n"
        "Bubble size = |flux| · color = signed direction (red=out, blue=in)",
        fontsize=13, fontweight="bold", pad=15,
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(-s_max, s_max))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.08, label="Signed Flux [m³/s]")
    cbar.ax.tick_params(labelsize=8)

    ax.view_init(elev=22, azim=-55)

    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Concept 3 → {out}")


# ---------------------------------------------------------------------------
# CONCEPT 4 — Unrolled Surface Map
#   X = axial position, Y = angular position (0°–360°)
#   Bubbles colored by signed flux, sized by absolute flux
#   Naturally handles coil holes that live at arbitrary angles
# ---------------------------------------------------------------------------

def concept_4(df: pd.DataFrame, stent_length: float,
              sidecar: Optional[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 5), facecolor="white")

    # Determine angular position for each hole
    angles = []
    if sidecar:
        hole_map = {h["hole_id"]: h for h in sidecar.get("holes", [])}
    else:
        hole_map = {}

    for i, (_, row) in enumerate(df.iterrows()):
        h = hole_map.get(row["hole_id"])
        if h and h.get("arc_deg") is not None:
            angles.append(float(h["arc_deg"]))
        elif h and "center_mm" in h:
            cy, cz = h["center_mm"][1], h["center_mm"][2]
            angles.append(math.degrees(math.atan2(cz, cy)) % 360)
        else:
            angles.append((i % 2) * 90.0)

    df_plot = df.copy()
    df_plot["angle_deg"] = angles

    abs_vals = df_plot["abs_flux"].values
    max_abs = abs_vals.max() if abs_vals.max() > 0 else 1.0
    sizes = 100 + 600 * (abs_vals / max_abs)

    signed = df_plot["signed_flux"].values
    s_max = max(abs(signed.min()), abs(signed.max())) if len(signed) > 0 else 1.0

    cmap = plt.cm.RdBu_r
    norm = plt.Normalize(-s_max, s_max)

    # Background region bands
    spans = region_spans(df)
    for region in ("prox", "mid", "dist"):
        if region not in spans:
            continue
        lo, hi = spans[region]
        ax.axvspan(lo - 3, hi + 3, color=REGION_COLORS_LIGHT[region], alpha=0.35, zorder=0)

    sc = ax.scatter(
        df_plot["axial_x_mm"], df_plot["angle_deg"],
        s=sizes, c=signed, cmap=cmap, norm=norm,
        edgecolors="white", linewidths=0.8, alpha=0.9, zorder=4,
    )

    for _, row in df_plot.iterrows():
        ax.annotate(
            row["hole_id"].split("_", 1)[-1],
            (row["axial_x_mm"], row["angle_deg"]),
            textcoords="offset points", xytext=(0, 12),
            fontsize=7, ha="center", color="#475569",
        )

    # Stent body outline hint
    ax.axhline(0, color=TUBE_EDGE_COLOR, linewidth=0.5, alpha=0.3, linestyle=":")
    ax.axhline(90, color=TUBE_EDGE_COLOR, linewidth=0.5, alpha=0.3, linestyle=":")
    ax.axhline(180, color=TUBE_EDGE_COLOR, linewidth=0.5, alpha=0.3, linestyle=":")
    ax.axhline(270, color=TUBE_EDGE_COLOR, linewidth=0.5, alpha=0.3, linestyle=":")

    for bx in section_boundaries(df):
        ax.axvline(bx, color="#e2e8f0", linewidth=1.2, linestyle="--")

    ax.set_xlabel("Axial Position  [mm]", fontsize=11)
    ax.set_ylabel("Angular Position  [°]", fontsize=11)
    ax.set_ylim(-30, 390)
    ax.set_yticks([0, 90, 180, 270, 360])
    ax.set_title(
        "Concept 4 — Unrolled Surface Map\n"
        "Stent surface flattened · bubble size = |flux| · color = signed direction",
        fontsize=13, fontweight="bold", pad=12,
    )

    cbar = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02, label="Signed Flux [m³/s]")
    cbar.ax.tick_params(labelsize=8)

    fig.tight_layout()
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Concept 4 → {out}")


# ---------------------------------------------------------------------------
# CONCEPT 5 — Regional Dashboard
#   4-panel layout: per-hole bar, regional totals, stent schematic, stats
# ---------------------------------------------------------------------------

def concept_5(df: pd.DataFrame, stent_length: float, r_outer: float,
              out: Path) -> None:
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)

    # Panel A: per-hole signed flux bars
    ax_a = fig.add_subplot(gs[0, 0])
    hole_ids = df["hole_id"].tolist()
    xs = np.arange(len(hole_ids))
    colors = [REGION_COLORS[r] for r in df["region"]]
    ax_a.bar(xs, df["signed_flux"], color=colors, edgecolor="white",
             linewidth=0.5, width=0.7, alpha=0.85)
    ax_a.axhline(0, color="#334155", linewidth=0.6)
    ax_a.set_xticks(xs)
    ax_a.set_xticklabels(
        [h.replace("shaft_", "") for h in hole_ids],
        rotation=50, ha="right", fontsize=7,
    )
    ax_a.set_ylabel("Signed Flux [m³/s]", fontsize=10)
    ax_a.set_title("A · Per-Hole Signed Flux", fontsize=11, fontweight="bold")
    ax_a.grid(axis="y", alpha=0.15)

    # Panel B: per-hole absolute flux bars
    ax_b = fig.add_subplot(gs[0, 1])
    ax_b.bar(xs, df["abs_flux"], color=colors, edgecolor="white",
             linewidth=0.5, width=0.7, alpha=0.85)
    ax_b.set_xticks(xs)
    ax_b.set_xticklabels(
        [h.replace("shaft_", "") for h in hole_ids],
        rotation=50, ha="right", fontsize=7,
    )
    ax_b.set_ylabel("Absolute Flux [m³/s]", fontsize=10)
    ax_b.set_title("B · Per-Hole Absolute Flux", fontsize=11, fontweight="bold")
    ax_b.grid(axis="y", alpha=0.15)

    # Panel C: regional totals
    ax_c = fig.add_subplot(gs[1, 0])
    totals = df.groupby("region").agg(
        signed_total=("signed_flux", "sum"),
        abs_total=("abs_flux", "sum"),
        n_holes=("hole_id", "count"),
    ).reindex(["prox", "mid", "dist"])

    bar_w = 0.35
    rx = np.arange(len(totals))
    ax_c.bar(rx - bar_w / 2, totals["signed_total"], bar_w,
             color=[REGION_COLORS[r] for r in totals.index],
             edgecolor="white", linewidth=0.5, label="Signed", alpha=0.75)
    ax_c.bar(rx + bar_w / 2, totals["abs_total"], bar_w,
             color=[REGION_COLORS[r] for r in totals.index],
             edgecolor="white", linewidth=0.5, label="Absolute",
             alpha=0.45, hatch="//")
    ax_c.axhline(0, color="#334155", linewidth=0.6)
    ax_c.set_xticks(rx)
    ax_c.set_xticklabels([f"{REGION_LABELS[r]}\n(n={totals.loc[r, 'n_holes']})"
                           for r in totals.index], fontsize=9)
    ax_c.set_ylabel("Total Flux [m³/s]", fontsize=10)
    ax_c.set_title("C · Regional Totals", fontsize=11, fontweight="bold")
    ax_c.legend(fontsize=8, loc="upper right")
    ax_c.grid(axis="y", alpha=0.15)

    # Panel D: stent schematic with annotations
    ax_d = fig.add_subplot(gs[1, 1])
    body = mpatches.FancyBboxPatch(
        (0, -0.35), stent_length, 0.7,
        boxstyle=mpatches.BoxStyle.Round(pad=0.12),
        facecolor=TUBE_BODY_COLOR, edgecolor=TUBE_EDGE_COLOR,
        linewidth=1.2, zorder=2,
    )
    ax_d.add_patch(body)

    px, py = pigtail_xy(0, "left")
    ax_d.plot(px, py * 0.12, color=PIGTAIL_COLOR, linewidth=1.8, alpha=0.5, zorder=1)
    dx, dy = pigtail_xy(stent_length, "right")
    ax_d.plot(dx, dy * 0.12, color=PIGTAIL_COLOR, linewidth=1.8, alpha=0.5, zorder=1)

    abs_vals = df["abs_flux"].values
    max_abs = abs_vals.max() if abs_vals.max() > 0 else 1.0

    for _, row in df.iterrows():
        s = 30 + 200 * (row["abs_flux"] / max_abs)
        ax_d.scatter(
            row["axial_x_mm"], 0, s=s,
            color=REGION_COLORS[row["region"]],
            edgecolors="white", linewidths=0.5, zorder=5,
        )

    ax_d.set_xlim(-PIGTAIL_HEIGHT - 3, stent_length + PIGTAIL_HEIGHT + 3)
    ax_d.set_ylim(-1.3, 1.3)
    ax_d.set_xlabel("Axial Position [mm]", fontsize=10)
    ax_d.set_yticks([])
    ax_d.spines["left"].set_visible(False)
    ax_d.set_title("D · Spatial Overview (bubble size ∝ |flux|)",
                    fontsize=11, fontweight="bold")

    fig.suptitle(
        "Concept 5 — Regional Dashboard",
        fontsize=15, fontweight="bold", y=1.01,
    )

    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Concept 5 → {out}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stent hole flux visualization concepts")
    ap.add_argument("csv", nargs="?", default=None,
                    help="Path to *_shaft_hole_flux.csv (omit for --demo)")
    ap.add_argument("--sidecar", default=None,
                    help="Path to .holes.json sidecar (auto-detected if omitted)")
    ap.add_argument("--output_dir", default=None,
                    help="Output directory (default: next to CSV or cwd)")
    ap.add_argument("--demo", action="store_true",
                    help="Use embedded demo data (design_0000 Test B results)")
    args = ap.parse_args()

    csv_path: Optional[Path] = None
    if args.csv:
        csv_path = Path(args.csv).resolve()
    elif not args.demo:
        ap.error("Provide a CSV path or use --demo")

    df = load_flux_csv(csv_path)

    sidecar_path = None
    if args.sidecar:
        sidecar_path = Path(args.sidecar).resolve()
    elif csv_path:
        candidate = csv_path.parent / csv_path.name.replace("_shaft_hole_flux.csv", ".holes.json")
        if candidate.exists():
            sidecar_path = candidate
    sidecar = load_sidecar(sidecar_path)

    stent_length = infer_stent_length(df, sidecar)
    r_outer = infer_r_outer(sidecar)

    if args.output_dir:
        out_dir = Path(args.output_dir).resolve()
    elif csv_path:
        out_dir = csv_path.parent
    else:
        out_dir = Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = csv_path.stem if csv_path else "demo"

    print(f"Loaded {len(df)} holes  ·  stent_length={stent_length:.1f}mm")
    print(f"Output → {out_dir}\n")

    concept_1(df, stent_length, r_outer, out_dir / f"{stem}_concept1_anatomical.png")
    concept_2(df, out_dir / f"{stem}_concept2_lollipop.png")
    concept_3(df, stent_length, r_outer, sidecar, out_dir / f"{stem}_concept3_3d_tube.png")
    concept_4(df, stent_length, sidecar, out_dir / f"{stem}_concept4_unrolled.png")
    concept_5(df, stent_length, r_outer, out_dir / f"{stem}_concept5_dashboard.png")

    print("\nDone — 5 concepts generated.")


if __name__ == "__main__":
    main()
