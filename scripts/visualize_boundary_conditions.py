#!/usr/bin/env python3
"""
Visualize Simulation Boundary Conditions and Geometry
Generates plots for the Peristalsis Analysis document.
"""
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Setup
OUTPUT_DIR = Path("docs/images")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------
# 1. Peristaltic Wave Function (flc2hs approximation)
# ---------------------------------------------------------
def flc2hs(x, scale):
    """Smoothed Heaviside function (COMSOL flc2hs equivalent)."""
    # Simple sigmoid approximation for visualization
    # flc2hs goes from 0 to 1 over interval 2*scale
    # Centered at x=0
    
    # We'll use tanh for a similar smooth step
    # tanh goes -1 to 1. We want 0 to 1.
    # 0.5 * (tanh(x/scale) + 1)
    
    # Actually, let's implement the piecewise polynomial for accuracy if possible
    # But tanh is close enough for "visual explanation"
    return 0.5 * (np.tanh(x / scale) + 1)

def plot_peristaltic_wave():
    t = 0 # Snapshot at t=0
    z = np.linspace(0, 0.15, 1000) # 15 cm ureter
    
    # Parameters
    P0 = 3500 # Pa
    v = 0.025 # 2.5 cm/s
    L_wave = 0.05 # 5 cm
    z0 = 0.02 # Start localion
    d = 0.003 # Smoothing 3mm
    
    # Wave function: P0 * (H(start) - H(end))
    # z axis is usually longitudinal. Wave travels +z? Or -z?
    # Let's say travels +z (kidney to bladder)
    p_wave = P0 * (flc2hs(z - (z0 + v*t), d) - flc2hs(z - (z0 + v*t) - L_wave, d))
    
    plt.figure(figsize=(10, 4))
    plt.plot(z*100, p_wave, 'b-', linewidth=2)
    plt.title("Peristaltic Pressure Wave (t=0)", fontsize=14)
    plt.xlabel("Ureter Length (cm)", fontsize=12)
    plt.ylabel("Pressure (Pa)", fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.fill_between(z*100, p_wave, color='blue', alpha=0.1)
    plt.annotate(f"Peak: {P0} Pa", xy=(4.5, 3500), xytext=(6, 3000), arrowprops=dict(arrowstyle="->"))
    plt.annotate(f"Wave Length: {L_wave*100} cm", xy=(4.5, 1000), xytext=(4.5, 1000))
    
    # Save
    path = OUTPUT_DIR / "peristalsis_wave.png"
    plt.savefig(path, dpi=150, bbox_inches='tight')
    print(f"Generated {path}")
    plt.close()

# ---------------------------------------------------------
# 2. Cough Impulse Function ("Water Hammer")
# ---------------------------------------------------------
def plot_cough_impulse():
    t = np.linspace(0, 1.0, 500)
    t0 = 0.2 # Cough at 0.2s
    sigma = 0.05 # Width
    P_peak = 10000 # 10 kPa
    
    p_cough = P_peak * np.exp(-((t - t0)**2) / (2 * sigma**2))
    
    plt.figure(figsize=(10, 4))
    plt.plot(t, p_cough/1000, 'r-', linewidth=2) # plot in kPa
    plt.title("Cough Impulse Pressure (Bladder)", fontsize=14)
    plt.xlabel("Time (s)", fontsize=12)
    plt.ylabel("Pressure (kPa)", fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.fill_between(t, p_cough/1000, color='red', alpha=0.1)
    plt.annotate(f"Peak: {P_peak/1000} kPa\n(Dangerous Reflux)", xy=(0.2, 10), xytext=(0.4, 8), arrowprops=dict(arrowstyle="->"))
    
    # Save
    path = OUTPUT_DIR / "cough_impulse.png"
    plt.savefig(path, dpi=150, bbox_inches='tight')
    print(f"Generated {path}")
    plt.close()

# ---------------------------------------------------------
# 3. Geometry Schematic (2D Proxy)
# ---------------------------------------------------------
def plot_geometry_schematic():
    # Create a cartoon of the ureter and stent
    plt.figure(figsize=(8, 6))
    
    # Ureter Walls (Gray)
    plt.plot([-1.5, -1.5], [0, 15], 'k-', linewidth=3, color='gray')
    plt.plot([1.5, 1.5], [0, 15], 'k-', linewidth=3, color='gray')
    
    # Stent Body (Blue)
    plt.plot([-0.7, -0.7], [1, 14], 'b-', linewidth=2) # Left wall
    plt.plot([0.7, 0.7], [1, 14], 'b-', linewidth=2)  # Right wall
    
    # Pigtails (Circles roughly)
    theta = np.linspace(0, 2*np.pi, 100)
    # Kidney coil
    xc_k = 1.5 * np.cos(theta)
    yc_k = 14 + 1.5 + 1.5 * np.sin(theta)
    plt.plot(xc_k, yc_k, 'b-', linewidth=2)
    
    # Bladder coil
    xc_b = 1.5 * np.cos(theta)
    yc_b = 1 - 1.5 + 1.5 * np.sin(theta)
    plt.plot(xc_b, yc_b, 'b-', linewidth=2)
    
    # Side holes
    for y in np.linspace(2, 13, 10):
        circle = plt.Circle((-0.7, y), 0.1, color='white', zorder=10) # hole on left
        plt.gca().add_patch(circle)
        circle = plt.Circle((0.7, y+0.5), 0.1, color='white', zorder=10) # hole on right
        plt.gca().add_patch(circle)

    plt.xlim(-5, 5)
    plt.ylim(-2, 17)
    plt.axis('off')
    plt.title("Geometric Domain Schematic", fontsize=14)
    
    # Annotations
    plt.text(-4, 15, "Kidney (Inlet)\nP ~ 100 Pa", fontsize=10)
    plt.text(-4, 0, "Bladder (Outlet)\nP ~ 0 Pa\n(Cough ~ 10 kPa)", fontsize=10)
    plt.text(2, 7.5, "Ureter Wall\n(Arruda-Boyce)\nMoving Mesh", fontsize=10, color='gray')
    plt.text(0, 7.5, "Stent\n(Elastic)", fontsize=10, color='blue', ha='center')
    
    # Save
    path = OUTPUT_DIR / "geometry_schematic.png"
    plt.savefig(path, dpi=150, bbox_inches='tight')
    print(f"Generated {path}")
    plt.close()

def main():
    plot_peristaltic_wave()
    plot_cough_impulse()
    plot_geometry_schematic()

if __name__ == "__main__":
    main()
