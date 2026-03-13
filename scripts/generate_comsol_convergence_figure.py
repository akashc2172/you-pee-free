#!/usr/bin/env python3
"""Generate a single scientific convergence figure from the COMSOL continuation log."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def build_data() -> dict[float, dict[str, list[float]]]:
    return {
        0.1: {
            "iter": list(range(1, 33)),
            "res": [
                1.4e4, 9.2e3, 1.1e4, 1.3e4, 1.5e4, 1.3e4, 1.9e4, 5.5e3,
                2.3e3, 1.6e3, 1.1e3, 7.8e2, 5.6e2, 3.9e2, 2.8e2, 1.8e2,
                1.2e2, 95, 84, 76, 68, 59, 49, 39, 29, 20, 13, 8.1, 7.3,
                4.2, 4.7, 6.8,
            ],
            "sol": [
                0.95, 0.57, 0.34, 0.32, 0.28, 0.25, 0.22, 0.14,
                0.12, 0.095, 0.082, 0.068, 0.058, 0.048, 0.041, 0.035,
                0.029, 0.024, 0.021, 0.019, 0.016, 0.014, 0.011, 0.0087,
                0.0062, 0.0041, 0.0023, 0.0011, 0.00049, 0.00022, 9.8e-5, 6.6e-5,
            ],
        },
        0.5: {
            "iter": list(range(1, 51)),
            "res": [
                3.8e3, 2.0e3, 1.1e4, 1.6e4, 9.0e4, 9.7e4, 7.1e4, 5.0e4, 2.7e4, 1.6e4,
                1.2e4, 1.4e4, 1.4e4, 1.0e4, 6.4e3, 6.4e3, 4.2e3, 2.7e3, 2.1e3, 1.7e3,
                1.0e3, 6.7e2, 5.1e2, 4.1e2, 4.0e2, 3.3e2, 3.0e2, 2.9e2, 2.7e2, 3.5e2,
                5.0e2, 3.7e2, 3.6e2, 3.3e2, 3.5e2, 4.2e2, 3.2e2, 4.5e2, 2.4e2, 2.0e2,
                1.5e2, 1.0e2, 68, 38, 18, 7.8, 3.6, 2.0, 0.96, 1.1,
            ],
            "sol": [
                0.71, 0.18, 0.35, 0.57, 0.66, 1.5, 1.8, 1.5, 1.4, 1.4,
                0.86, 0.70, 0.57, 0.44, 0.38, 0.36, 0.30, 0.27, 0.27, 0.20,
                0.16, 0.11, 0.10, 0.085, 0.079, 0.073, 0.061, 0.058, 0.060, 0.062,
                0.089, 0.078, 0.067, 0.056, 0.066, 0.071, 0.058, 0.076, 0.073, 0.067,
                0.054, 0.035, 0.023, 0.013, 0.0057, 0.0024, 0.00081, 0.00042, 0.00018, 0.00035,
            ],
        },
        1.0: {
            "iter": list(range(1, 138)),
            "res": [
                4.7e3, 7.9e3, 6.7e3, 4.6e3, 9.6e3, 8.8e3, 6.0e3, 3.6e3, 2.7e3, 2.8e3,
                2.8e3, 1.6e3, 8.4e2, 7.0e2, 4.0e2, 4.0e2, 1.9e2, 1.9e2, 2.1e2, 2.3e2,
                2.5e2, 2.6e2, 2.6e2, 2.5e2, 1.9e2, 2.2e2, 3.3e2, 5.0e2, 5.3e2, 7.2e2,
                1.2e3, 1.5e3, 2.2e3, 1.6e3, 4.5e3, 4.1e3, 3.1e3, 4.9e4, 4.4e4, 4.9e4,
                1.1e5, 8.4e4, 5.4e4, 4.0e4, 2.8e4, 2.5e4, 2.5e4, 3.0e4, 2.1e4, 1.4e4,
                8.2e3, 6.1e3, 9.7e3, 6.4e3, 3.5e3, 3.0e3, 2.0e3, 1.6e3, 7.9e2, 8.3e2,
                4.6e2, 2.4e2, 1.1e2, 80, 81, 99, 1.2e2, 1.4e2, 2.1e2, 2.7e2,
                2.8e2, 2.7e2, 2.6e2, 2.7e2, 2.2e2, 1.9e2, 2.5e2, 4.2e2, 6.1e2, 6.4e2,
                1.2e3, 1.8e3, 4.2e3, 3.3e3, 2.8e3, 2.1e3, 3.7e3, 4.0e3, 1.3e4, 2.7e4,
                2.3e4, 1.1e5, 4.0e5, 4.5e5, 2.7e5, 2.4e5, 1.9e5, 1.0e5, 8.6e4, 4.8e4,
                3.7e4, 2.3e4, 4.3e4, 2.7e4, 1.9e4, 1.7e4, 2.4e4, 4.1e4, 3.6e4, 3.2e4,
                1.8e4, 9.6e3, 6.6e3, 6.2e3, 6.4e3, 5.9e3, 4.4e3, 3.7e3, 2.6e3, 1.7e3,
                1.2e3, 8.0e2, 5.9e2, 5.3e2, 4.6e2, 4.0e2, 3.4e2, 2.7e2, 2.3e2, 1.6e2,
                1.5e2, 1.1e2, 1.4e2, 77, 1.1e2, 51, 66,
            ],
            "sol": [
                0.15, 0.15, 0.16, 0.15, 0.23, 0.29, 0.26, 0.22, 0.17, 0.18,
                0.16, 0.12, 0.11, 0.083, 0.060, 0.057, 0.044, 0.029, 0.026, 0.023,
                0.023, 0.021, 0.020, 0.020, 0.018, 0.020, 0.030, 0.038, 0.034, 0.037,
                0.053, 0.072, 0.097, 0.090, 0.14, 0.15, 0.12, 0.28, 0.49, 0.58,
                0.77, 0.82, 0.63, 0.62, 0.51, 0.43, 0.35, 0.33, 0.27, 0.25,
                0.21, 0.15, 0.17, 0.17, 0.13, 0.12, 0.12, 0.12, 0.082, 0.11,
                0.068, 0.058, 0.036, 0.020, 0.011, 0.012, 0.013, 0.016, 0.021, 0.027,
                0.029, 0.025, 0.021, 0.021, 0.020, 0.018, 0.024, 0.035, 0.042, 0.039,
                0.047, 0.070, 0.12, 0.13, 0.10, 0.092, 0.10, 0.15, 0.27, 0.45,
                0.47, 0.53, 1.2, 1.6, 1.4, 1.2, 1.1, 0.98, 0.94, 1.0,
                1.1, 0.65, 0.75, 0.72, 0.59, 0.55, 0.42, 0.37, 0.31, 0.24,
                0.22, 0.20, 0.20, 0.20, 0.18, 0.16, 0.14, 0.12, 0.098, 0.083,
                0.074, 0.066, 0.041, 0.030, 0.028, 0.024, 0.026, 0.029, 0.025, 0.022,
                0.018, 0.014, 0.010, 0.0080, 0.0061, 0.0046, 0.0034,
            ],
        },
    }


def make_figure(output_base: Path) -> tuple[Path, Path]:
    data = build_data()
    colors = {0.1: "#12727c", 0.5: "#3e8057", 1.0: "#a94040"}

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "legend.fontsize": 10,
        }
    )

    fig, ax = plt.subplots(figsize=(11.5, 6.5), constrained_layout=True)

    for p_ramp, stage in data.items():
        x = np.array(stage["iter"])
        y = np.array(stage["res"], dtype=float)
        ax.plot(x, y, marker="o", markersize=3.0, linewidth=2.2, color=colors[p_ramp], label=f"p_ramp = {p_ramp:g}")

    ax.set_yscale("log")
    ax.set_xlabel("Nonlinear iteration within continuation stage")
    ax.set_ylabel("Residual estimate (ResEst)")
    ax.set_title("COMSOL Continuation Convergence by Pressure-Ramp Stage", loc="left", fontweight="bold")
    ax.grid(True, which="major", alpha=0.25)
    ax.grid(True, which="minor", alpha=0.08)

    ax.legend(frameon=False, loc="upper right")

    ax.text(
        0.02,
        0.97,
        "Stationary laminar solve with continuation in inlet pressure\n"
        "Interpretation: 0.1 converges cleanly, 0.5 converges after a mid-stage residual spike,\n"
        "1.0 shows repeated instability and large residual excursions.",
        transform=ax.transAxes,
        va="top",
        fontsize=10.5,
        color="#5c656e",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#f6f8fa", edgecolor="#d9e1e8"),
    )

    ax.annotate(
        "clean early-stage descent",
        xy=(18, 95),
        xytext=(7, 240),
        arrowprops=dict(arrowstyle="->", color=colors[0.1], lw=1.5),
        fontsize=10,
        color=colors[0.1],
    )
    ax.annotate(
        "mid-stage spike,\nthen recovery",
        xy=(5, 9.0e4),
        xytext=(12, 2.3e4),
        arrowprops=dict(arrowstyle="->", color=colors[0.5], lw=1.5),
        fontsize=10,
        color=colors[0.5],
    )
    ax.annotate(
        "full-load instability",
        xy=(38, 4.9e4),
        xytext=(58, 1.2e5),
        arrowprops=dict(arrowstyle="->", color=colors[1.0], lw=1.5),
        fontsize=10,
        color=colors[1.0],
    )

    fig.suptitle("Residual Convergence from Actual COMSOL Log", fontsize=18, fontweight="bold", color="#152438")

    png_path = output_base.with_suffix(".png")
    svg_path = output_base.with_suffix(".svg")
    fig.savefig(png_path, dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png_path, svg_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a COMSOL continuation convergence figure.")
    parser.add_argument(
        "--output-base",
        default="docs/images/peristalsis_figure_pack/fig17_comsol_continuation_convergence",
        help="Output path without extension",
    )
    args = parser.parse_args()

    output_base = Path(args.output_base)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    png_path, svg_path = make_figure(output_base)
    print(png_path)
    print(svg_path)


if __name__ == "__main__":
    main()
