#!/usr/bin/env python3
"""Generate a scientific figure for the Tier A middle-cylinder load model."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch


CMH2O_TO_PA = 98.0665


def p_ext(z_mm: np.ndarray, t_s: np.ndarray, p0_cmh2o: float, a_cmh2o: float, wavelength_mm: float, freq_hz: float) -> np.ndarray:
    k = 2.0 * np.pi / wavelength_mm
    omega = 2.0 * np.pi * freq_hz
    return p0_cmh2o + a_cmh2o * np.sin(k * z_mm - omega * t_s)


def make_three_cylinder_schematic(ax) -> None:
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    specs = [
        (0.5, 1.45, 2.1, 1.0, "#cfe5ff", "Proximal\nkidney-side"),
        (2.95, 1.32, 4.1, 1.25, "#d2f4e5", "Middle cylinder\nTier A load region"),
        (7.35, 1.45, 2.1, 1.0, "#ffe7ca", "Distal\nbladder-side"),
    ]
    for x, y, w, h, color, label in specs:
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.18",
            facecolor=color,
            edgecolor="white",
            linewidth=2.0,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10, fontweight="bold", color="#152438")

    ax.plot([0.8, 9.1], [1.95, 1.95], color="#152438", linewidth=6, solid_capstyle="round")
    ax.text(5.0, 0.72, "Imported stent passes through all three fluid regions", ha="center", fontsize=10, color="#5c656e")

    for x in np.linspace(3.2, 6.8, 6):
        ax.arrow(
            x,
            3.25,
            0,
            -0.45,
            width=0.03,
            head_width=0.22,
            head_length=0.12,
            color="#c68a18",
            length_includes_head=True,
        )
    ax.text(5.0, 3.45, "Tier A external load acts only on the middle cylinder", ha="center", fontsize=10, color="#c68a18", fontweight="bold")


def generate_figure(output_base: Path) -> tuple[Path, Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.titlesize": 12,
        }
    )

    # Illustrative planning values only, not fitted data.
    p0_cmh2o = 2.5
    a_cmh2o = 7.5
    wavelength_mm = 50.0
    freq_hz = 4.0 / 60.0
    z_probe_mm = 75.0

    fig = plt.figure(figsize=(14, 8), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], width_ratios=[1.05, 1.0])

    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    make_three_cylinder_schematic(ax0)
    ax0.set_title("A. Middle-cylinder-only Tier A loading concept", loc="left")

    ax1.axis("off")
    ax1.set_title("B. Governing load form", loc="left")
    ax1.text(0.03, 0.75, r"$P_{\mathrm{ext}}(z,t)=P_0 + A\sin(kz-\omega t)$", fontsize=20, weight="bold", color="#152438")
    lines = [
        r"$P_0$ : baseline tissue confinement pressure",
        r"$A$ : peristaltic amplitude",
        r"$k=2\pi/\lambda$ : spatial wave number",
        r"$\omega=2\pi f$ : temporal frequency",
        r"$z$ : axial coordinate along middle cylinder only",
    ]
    y = 0.58
    for line in lines:
        ax1.text(0.05, y, line, fontsize=12, color="#171b1f")
        y -= 0.11
    ax1.text(
        0.03,
        0.08,
        "Illustrative planning values shown here:\n"
        f"$P_0$ = {p0_cmh2o:.1f} cm H$_2$O ({p0_cmh2o * CMH2O_TO_PA:.0f} Pa), "
        f"$A$ = {a_cmh2o:.1f} cm H$_2$O, $\\lambda$ = {wavelength_mm:.0f} mm, "
        "f = 4/min\nThese are schematic Tier A values, not completed experimental fits.",
        fontsize=10.5,
        color="#5c656e",
    )

    t = np.linspace(0, 30, 500)
    p_t = p_ext(np.full_like(t, z_probe_mm), t, p0_cmh2o, a_cmh2o, wavelength_mm, freq_hz)
    ax2.plot(t, p_t, color="#12727c", linewidth=2.6)
    ax2.axhline(p0_cmh2o, color="#5c656e", linestyle="--", linewidth=1.2, label=r"$P_0$")
    ax2.set_title("C. Temporal load at a fixed middle-cylinder location", loc="left")
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("External load (cm H$_2$O)")
    ax2.grid(True, alpha=0.25)
    ax2.legend(frameon=False, loc="upper right")
    ax2.text(
        0.02,
        0.05,
        f"Example probe location: z = {z_probe_mm:.0f} mm",
        transform=ax2.transAxes,
        fontsize=10,
        color="#5c656e",
    )

    z = np.linspace(0, 150, 360)
    t_heat = np.linspace(0, 30, 240)
    Z, T = np.meshgrid(z, t_heat)
    P = p_ext(Z, T, p0_cmh2o, a_cmh2o, wavelength_mm, freq_hz)
    im = ax3.imshow(
        P,
        origin="lower",
        aspect="auto",
        extent=[z.min(), z.max(), t_heat.min(), t_heat.max()],
        cmap="viridis",
    )
    ax3.set_title("D. Traveling-wave load over the middle cylinder", loc="left")
    ax3.set_xlabel("Axial coordinate z (mm)")
    ax3.set_ylabel("Time (s)")
    cbar = fig.colorbar(im, ax=ax3, fraction=0.046, pad=0.03)
    cbar.set_label("External load (cm H$_2$O)")

    fig.suptitle("Tier A Middle-Cylinder Tissue Load Schematic", fontsize=18, fontweight="bold", color="#152438")

    png_path = output_base.with_suffix(".png")
    svg_path = output_base.with_suffix(".svg")
    fig.savefig(png_path, dpi=220, bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png_path, svg_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Tier A load figure.")
    parser.add_argument(
        "--output-base",
        default="docs/images/peristalsis_figure_pack/fig16_tierA_middle_cylinder_load",
        help="Output path without extension",
    )
    args = parser.parse_args()

    output_base = Path(args.output_base)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    png_path, svg_path = generate_figure(output_base)
    print(png_path)
    print(svg_path)


if __name__ == "__main__":
    main()
