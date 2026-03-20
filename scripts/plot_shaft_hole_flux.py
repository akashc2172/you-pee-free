#!/usr/bin/env python3
"""Analyze and plot COMSOL per-hole shaft flux CSV exports.

Usage:
    python scripts/plot_shaft_hole_flux.py design_0000.hole_fluxes.csv
    python scripts/plot_shaft_hole_flux.py design_0000.hole_fluxes.csv --output_dir results/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REGION_ORDER = {"prox": 0, "mid": 1, "dist": 2}
STEP_LABELS = {0: "p_ramp=0.1", 1: "p_ramp=0.5", 2: "p_ramp=1.0"}
STEP_COLORS = {0: "#999999", 1: "#4c78a8", 2: "#e45756"}


def load_flux_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    return df


def add_axial_order(df: pd.DataFrame) -> pd.DataFrame:
    """Infer axial ordering from region + numeric suffix in hole_id."""
    df = df.copy()
    df["_region_rank"] = df["region"].map(REGION_ORDER).fillna(99).astype(int)
    df["_suffix"] = df["hole_id"].str.extract(r"(\d+)$").astype(int)
    df = df.sort_values(["_region_rank", "_suffix"]).reset_index(drop=True)
    df["axial_rank"] = df.groupby("step_index").cumcount()
    df.drop(columns=["_region_rank", "_suffix"], inplace=True)
    return df


def step_label(idx: int) -> str:
    return STEP_LABELS.get(idx, f"step={idx}")


def step_color(idx: int) -> str:
    return STEP_COLORS.get(idx, "#333333")


def plot_flux_by_hole(df: pd.DataFrame, col: str, title: str, ylabel: str,
                      out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    steps = sorted(df["step_index"].unique())
    hole_order = (
        df[df["step_index"] == steps[-1]]
        .sort_values("axial_rank")["hole_id"]
        .tolist()
    )
    x_positions = range(len(hole_order))
    id_to_x = {h: i for i, h in enumerate(hole_order)}

    for s in steps:
        sub = df[df["step_index"] == s].copy()
        xs = [id_to_x[h] for h in sub["hole_id"] if h in id_to_x]
        ys = [sub.loc[sub["hole_id"] == h, col].values[0] for h in sub["hole_id"] if h in id_to_x]
        ax.plot(xs, ys, marker="o", label=step_label(s), color=step_color(s),
                linewidth=1.5, markersize=5)

    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(hole_order, rotation=55, ha="right", fontsize=7)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    ax.axhline(0, color="black", linewidth=0.5)

    region_boundaries = []
    prev_region = None
    for i, h in enumerate(hole_order):
        region = h.split("_")[1]
        if prev_region is not None and region != prev_region:
            region_boundaries.append(i - 0.5)
        prev_region = region
    for b in region_boundaries:
        ax.axvline(b, color="grey", linewidth=0.8, linestyle="--", alpha=0.5)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"  saved: {out_path}")


def plot_regional_totals(df: pd.DataFrame, col: str, title: str, ylabel: str,
                         out_path: Path) -> None:
    totals = df.groupby(["step_index", "region"])[col].sum().reset_index()
    totals["_region_rank"] = totals["region"].map(REGION_ORDER)
    totals = totals.sort_values(["step_index", "_region_rank"])

    fig, ax = plt.subplots(figsize=(7, 4.5))
    steps = sorted(totals["step_index"].unique())
    regions = sorted(totals["region"].unique(), key=lambda r: REGION_ORDER.get(r, 99))
    n_regions = len(regions)
    bar_width = 0.22
    offsets = [bar_width * (i - (len(steps) - 1) / 2) for i in range(len(steps))]

    for si, s in enumerate(steps):
        sub = totals[totals["step_index"] == s].set_index("region")
        vals = [sub.loc[r, col] if r in sub.index else 0 for r in regions]
        xs = [i + offsets[si] for i in range(n_regions)]
        ax.bar(xs, vals, width=bar_width, label=step_label(s), color=step_color(s))

    ax.set_xticks(range(n_regions))
    ax.set_xticklabels(regions)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    ax.axhline(0, color="black", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    print(f"  saved: {out_path}")


def print_summary(df: pd.DataFrame) -> None:
    steps = sorted(df["step_index"].unique())
    final_step = steps[-1]
    final = df[df["step_index"] == final_step].copy()

    print("\n" + "=" * 70)
    print(f"SUMMARY  (final step: {step_label(final_step)})")
    print("=" * 70)

    top_abs = final.nlargest(3, "flux_abs_m3_per_s")[["hole_id", "region", "flux_abs_m3_per_s"]]
    print("\nTop 3 holes by absolute flux:")
    for _, row in top_abs.iterrows():
        print(f"  {row['hole_id']:25s}  {row['region']:6s}  {row['flux_abs_m3_per_s']:.4e}")

    print("\nHoles that flip sign across steps:")
    for hole_id, grp in df.groupby("hole_id"):
        signs = grp.sort_values("step_index")["flux_signed_m3_per_s"].values
        has_pos = any(v > 0 for v in signs)
        has_neg = any(v < 0 for v in signs)
        if has_pos and has_neg:
            vals_str = ", ".join(f"{v:+.3e}" for v in signs)
            print(f"  {hole_id:25s}  [{vals_str}]")

    print("\nRegional totals by step:")
    for s in steps:
        sub = df[df["step_index"] == s]
        print(f"\n  {step_label(s)}:")
        for region in ["prox", "mid", "dist"]:
            rsub = sub[sub["region"] == region]
            if rsub.empty:
                continue
            signed_total = rsub["flux_signed_m3_per_s"].sum()
            abs_total = rsub["flux_abs_m3_per_s"].sum()
            print(f"    {region:6s}  signed={signed_total:+.4e}   abs={abs_total:.4e}   n={len(rsub)}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze COMSOL shaft-hole flux CSV")
    parser.add_argument("csv", help="Path to design_XXXX.hole_fluxes.csv")
    parser.add_argument("--output_dir", default=None,
                        help="Directory for plots (default: same as CSV)")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else csv_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = csv_path.stem.replace(".hole_fluxes", "")

    df = load_flux_csv(csv_path)
    df = add_axial_order(df)

    print(f"Loaded {len(df)} rows, {df['hole_id'].nunique()} holes, "
          f"{df['step_index'].nunique()} steps")

    print("\nPlots:")
    plot_flux_by_hole(df, "flux_signed_m3_per_s",
                      "Signed Flux vs Hole (axial order)",
                      "signed flux [m³/s]",
                      output_dir / f"{stem}_signed_vs_hole.png")

    plot_flux_by_hole(df, "flux_abs_m3_per_s",
                      "Absolute Flux vs Hole (axial order)",
                      "absolute flux [m³/s]",
                      output_dir / f"{stem}_abs_vs_hole.png")

    plot_regional_totals(df, "flux_signed_m3_per_s",
                         "Regional Signed Flux Totals",
                         "signed flux total [m³/s]",
                         output_dir / f"{stem}_regional_signed.png")

    plot_regional_totals(df, "flux_abs_m3_per_s",
                         "Regional Absolute Flux Totals",
                         "absolute flux total [m³/s]",
                         output_dir / f"{stem}_regional_abs.png")

    print_summary(df)


if __name__ == "__main__":
    main()
