"""
Stent CAD Generator using build123d.

This module provides the StentGenerator class for creating parametric stent
geometries with:
- Proximal and distal helical coils (independent parameters)
- Hollow tube body with configurable wall thickness
- Side holes in proximal, middle, and distal sections
- Unroofed (half-pipe) distal section option
- Coil holes for drainage at pigtail ends

Validated for COMSOL CFD import via STEP export.
"""

from build123d import *
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
import math


@dataclass
class StentParameters:
    """
    Stent design parameters with validation.
    
    Uses fraction-based sampling (r_t, r_sh, r_end) to guarantee valid geometry.
    Absolute dimensions are derived from these fractions.
    """
    # Primary dimensions
    stent_french: float = 6.0       # French size (1 Fr = 0.333 mm)
    stent_length: float = 150.0     # Total body length (mm)
    
    # Coil parameters (proximal)
    coil_R_prox: float = 6.0        # Coil radius (mm)
    pitch_prox: float = 6.0         # Helix pitch (mm)
    turns_prox: float = 1.5         # Number of helix turns
    
    # Coil parameters (distal)
    coil_R_dist: float = 6.0
    pitch_dist: float = 6.0
    turns_dist: float = 1.5
    
    # Fraction-based parameters (sampled 0-1, then derived)
    r_t: float = 0.15               # Wall thickness = r_t * OD
    r_sh: float = 0.50              # Side hole diameter = r_sh * ID (capped)
    r_end: float = 0.70             # End hole diameter = r_end * ID (capped)
    
    # Hole counts per section
    n_prox: int = 3
    n_mid: int = 6
    n_dist: int = 3
    
    # Section lengths (proximal and distal)
    section_length_prox: float = 30.0
    section_length_dist: float = 30.0
    
    # Unroofed (half-pipe) cut
    unroofed_length: float = 0.0
    
    # Coil hole t-parameters (where on helix to cut holes)
    coil_hole_params: List[float] = field(default_factory=lambda: [0.25, 0.5, 0.75])
    
    # Constants
    GAP_MIN: float = 0.3            # Minimum gap between holes (mm)
    BUFFER_MIN: float = 1.0         # Buffer from section ends (mm)
    CAP_MARGIN: float = 0.15        # d_sh <= ID - cap_margin (mm)
    ID_MIN: float = 0.6             # Minimum inner diameter (mm)
    
    def __post_init__(self):
        # Ensure integers for hole counts
        self.n_prox = int(self.n_prox)
        self.n_mid = int(self.n_mid)
        self.n_dist = int(self.n_dist)
        
        self._derive_and_validate()
    
    def _derive_and_validate(self):
        """Derive absolute dimensions and validate geometry."""
        # Derive from French size
        self.OD = 0.333 * self.stent_french
        self.wall_thickness = self.r_t * self.OD
        self.ID = self.OD - 2 * self.wall_thickness
        
        # Check minimum lumen
        if self.ID < self.ID_MIN:
            raise ValueError(f"ID ({self.ID:.2f}) < ID_MIN ({self.ID_MIN}). Reduce r_t or increase French.")
        
        # Derive hole diameters (capped)
        self.d_sh = min(self.r_sh * self.ID, self.ID - self.CAP_MARGIN)
        self.d_end = min(self.r_end * self.ID, self.ID - self.CAP_MARGIN)
        
        # Derive radii for CAD
        self.r_outer = self.OD / 2
        self.r_inner = self.ID / 2
        self.hole_radius = self.d_sh / 2
        
        # Derive middle section length
        self.section_length_mid = (
            self.stent_length 
            - self.section_length_prox 
            - self.section_length_dist
        )
        if self.section_length_mid < 10.0:
            raise ValueError(f"Middle section ({self.section_length_mid:.1f}mm) < 10mm. Reduce prox/dist sections.")
        
        # Validate hole packing in each section
        self._validate_hole_packing('prox', self.section_length_prox, self.n_prox)
        self._validate_hole_packing('mid', self.section_length_mid, self.n_mid)
        self._validate_hole_packing('dist', self.section_length_dist, self.n_dist)
        
        # Precompute hole positions along body
        self.hole_positions = self._compute_hole_positions()
    
    def _validate_hole_packing(self, section: str, length: float, n_holes: int):
        """Check if holes fit in section without overlap."""
        if n_holes == 0:
            return
        buffer = max(self.BUFFER_MIN, self.hole_radius)
        L_use = length - 2 * buffer
        pitch_min = self.d_sh + self.GAP_MIN
        required = n_holes * pitch_min
        if required > L_use:
            raise ValueError(
                f"Cannot fit {n_holes} holes in {section} section. "
                f"Required: {required:.1f}mm, Available: {L_use:.1f}mm. "
                f"Reduce n_{section} or hole diameter."
            )
    
    def _compute_hole_positions(self) -> List[float]:
        """Compute axial positions of all holes along the body."""
        positions = []
        buffer = max(self.BUFFER_MIN, self.hole_radius)
        
        # Proximal section: 0 to section_length_prox
        if self.n_prox > 0:
            start = buffer
            end = self.section_length_prox - buffer
            spacing = (end - start) / max(1, self.n_prox - 1) if self.n_prox > 1 else 0
            for i in range(self.n_prox):
                pos = start + i * spacing if self.n_prox > 1 else (start + end) / 2
                positions.append(pos)
        
        # Middle section: section_length_prox to section_length_prox + section_length_mid
        if self.n_mid > 0:
            mid_start = self.section_length_prox + buffer
            mid_end = self.section_length_prox + self.section_length_mid - buffer
            spacing = (mid_end - mid_start) / max(1, self.n_mid - 1) if self.n_mid > 1 else 0
            for i in range(self.n_mid):
                pos = mid_start + i * spacing if self.n_mid > 1 else (mid_start + mid_end) / 2
                positions.append(pos)
        
        # Distal section: (prox + mid) to stent_length
        if self.n_dist > 0:
            dist_start = self.section_length_prox + self.section_length_mid + buffer
            dist_end = self.stent_length - buffer
            spacing = (dist_end - dist_start) / max(1, self.n_dist - 1) if self.n_dist > 1 else 0
            for i in range(self.n_dist):
                pos = dist_start + i * spacing if self.n_dist > 1 else (dist_start + dist_end) / 2
                positions.append(pos)
        
        return positions


class StentGenerator:
    """
    Generate stent CAD geometry from parameters.
    
    Usage:
        params = StentParameters(stent_french=6.0, n_mid=8)
        generator = StentGenerator(params)
        solid = generator.generate()
        generator.export_step(Path("outputs/stent.step"))
    """
    
    def __init__(self, params: StentParameters):
        self.params = params
        self._solid: Optional[Part] = None
    
    def generate(self) -> Part:
        """Generate the complete stent solid."""
        p = self.params
        
        # 1. Generate helix paths
        prox_wire, body_start_pt, body_start_tan = self._make_prox_helix()
        body_wire, body_end_pt, body_end_tan = self._make_body(body_start_pt, body_start_tan)
        dist_wire = self._make_dist_helix(body_end_pt, body_end_tan)
        
        # 2. Generate outer solid (fused)
        outer_solid = self._build_solid(prox_wire, body_wire, dist_wire, p.r_outer)
        
        # 3. Generate inner solid (for hollowing)
        inner_solid = self._build_solid(prox_wire, body_wire, dist_wire, p.r_inner)
        
        # 4. Boolean subtraction → hollow stent
        hollow = outer_solid - inner_solid
        
        # 5. Unroofed cut (if enabled)
        if p.unroofed_length > 0:
            hollow = self._cut_unroofed(hollow, body_end_pt, body_end_tan)
        
        # 6. Cut holes
        hollow = self._cut_body_holes(hollow, body_start_pt, body_start_tan)
        if prox_wire:
            hollow = self._cut_coil_holes(hollow, prox_wire)
        if dist_wire:
            hollow = self._cut_coil_holes(hollow, dist_wire)
        
        self._solid = hollow
        return hollow
    
    def _make_prox_helix(self):
        """Create proximal helix path. Returns (wire, end_point, end_tangent)."""
        p = self.params
        if p.turns_prox <= 0:
            return None, Vector(0, 0, 0), Vector(1, 0, 0)
        
        height = p.pitch_prox * p.turns_prox
        helix = Helix(pitch=p.pitch_prox, height=height, radius=p.coil_R_prox)
        wire = Wire([helix.edges()[0]])
        
        end_edge = wire.edges()[-1]
        end_pt = end_edge.end_point()
        end_tan = end_edge.tangent_at(1)
        
        return wire, end_pt, end_tan
    
    def _make_body(self, start_pt: Vector, start_tan: Vector):
        """Create straight body path. Returns (wire, end_point, end_tangent)."""
        end_pt = start_pt + (start_tan * self.params.stent_length)
        wire = Polyline([start_pt, end_pt]).wires()[0]
        return wire, end_pt, start_tan  # Tangent unchanged for straight line
    
    def _make_dist_helix(self, body_end_pt: Vector, body_end_tan: Vector):
        """Create distal helix path, transformed to attach at body end."""
        p = self.params
        if p.turns_dist <= 0:
            return None
        
        height = p.pitch_dist * p.turns_dist
        helix = Helix(pitch=p.pitch_dist, height=height, radius=p.coil_R_dist)
        
        # Transform helix to attach at body end
        hs_pt = helix.edges()[0].start_point()
        hs_tan = helix.edges()[0].tangent_at(0)
        
        pl_src = Plane(origin=hs_pt, z_dir=hs_tan)
        pl_target = Plane(origin=body_end_pt, z_dir=body_end_tan)
        T = pl_target.location * pl_src.location.inverse()
        
        wire = Wire([helix.edges()[0]]).moved(T)
        return wire
    
    def _build_solid(self, prox_wire, body_wire, dist_wire, radius: float) -> Part:
        """Sweep a circle along all wires and fuse into one solid."""
        parts = []
        
        # Prox coil
        if prox_wire:
            parts.append(self._sweep_circle(prox_wire, radius))
        
        # Body
        if prox_wire:
            # Extrude from previous part's end face for perfect alignment
            parts.append(self._extrude_from_face(body_wire, radius, parts[-1]))
        else:
            parts.append(self._sweep_circle(body_wire, radius))
        
        # Dist coil
        if dist_wire:
            parts.append(self._sweep_circle(dist_wire, radius))
        
        # Fuse all
        result = parts[0]
        for p in parts[1:]:
            result = result + p
        return result
    
    def _sweep_circle(self, path: Wire, radius: float) -> Part:
        """Sweep a circle along a wire path."""
        start_edge = path.edges()[0]
        pt = start_edge.start_point()
        tan = start_edge.tangent_at(0)
        
        with BuildPart() as bp:
            with BuildSketch(Plane(origin=pt, z_dir=tan)):
                Circle(radius=radius)
            sweep(path=path)
        return bp.part
    
    def _extrude_from_face(self, path: Wire, radius: float, prev_part: Part) -> Part:
        """Extrude along path from the closest face of previous part."""
        start_pt = path.edges()[0].start_point()
        face = prev_part.faces().sort_by_distance(start_pt)[0]
        
        vec = path.edges()[0].end_point() - start_pt
        length = vec.length
        direction = vec.normalized()
        
        with BuildPart() as bp:
            add(face)
            extrude(amount=length, dir=direction)
        return bp.part
    
    def _cut_unroofed(self, solid: Part, body_end_pt: Vector, body_end_tan: Vector) -> Part:
        """Cut top half of distal section to create unroofed region."""
        p = self.params
        pl_end = Plane(origin=body_end_pt, z_dir=body_end_tan)
        
        box_w = p.r_outer * 4
        box_h = p.r_outer * 4
        
        cutter = Box(box_w, box_h, p.unroofed_length)
        align_loc = Location(Vector(0, box_h / 2, -p.unroofed_length / 2))
        cutter = cutter.moved(align_loc).moved(pl_end.location)
        
        return solid - cutter
    
    def _cut_body_holes(self, solid: Part, start_pt: Vector, axis: Vector) -> Part:
        """Cut side holes along the body at precomputed positions."""
        p = self.params
        axis = axis.normalized()
        
        # Compute perpendicular directions for alternating hole placement
        arb = Vector(1, 0, 0) if abs(axis.X) < 0.9 else Vector(0, 1, 0)
        v1 = axis.cross(arb).normalized()
        v2 = axis.cross(v1).normalized()
        
        with BuildPart() as bp:
            add(solid)
            for i, d in enumerate(p.hole_positions):
                center = start_pt + (axis * d)
                cut_dir = v1 if i % 2 == 0 else v2
                with BuildSketch(Plane(origin=center, z_dir=cut_dir)):
                    Circle(radius=p.hole_radius)
                # One-wall cut (both=False)
                extrude(amount=p.r_outer * 4, both=False, mode=Mode.SUBTRACT)
        return bp.part
    
    def _cut_coil_holes(self, solid: Part, wire: Wire) -> Part:
        """Cut holes at specified t-parameters along a coil wire."""
        p = self.params
        result = solid
        
        for t_val in p.coil_hole_params:
            try:
                loc = wire.location_at(t_val)
                cut_plane = Plane(origin=loc.position, z_dir=loc.x_axis)
                with BuildPart() as bp:
                    add(result)
                    with BuildSketch(cut_plane):
                        Circle(radius=p.hole_radius)
                    extrude(amount=p.r_outer * 3, both=False, mode=Mode.SUBTRACT)
                result = bp.part
            except Exception:
                pass  # Skip if location fails
        return result
    
    def export_step(self, path: Path):
        """Export to STEP format (for COMSOL import)."""
        if self._solid is None:
            self.generate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_step(self._solid, str(path))
    
    def export_stl(self, path: Path):
        """Export to STL format (for visualization)."""
        if self._solid is None:
            self.generate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_stl(self._solid, str(path))
    
    def get_info(self) -> dict:
        """Return summary of stent geometry."""
        p = self.params
        return {
            "French": p.stent_french,
            "OD (mm)": round(p.OD, 3),
            "ID (mm)": round(p.ID, 3),
            "Wall (mm)": round(p.wall_thickness, 3),
            "Body Length (mm)": p.stent_length,
            "Total Holes": len(p.hole_positions),
            "Hole Positions": [round(x, 1) for x in p.hole_positions],
            "Unroofed (mm)": p.unroofed_length,
        }


if __name__ == "__main__":
    # Quick test
    params = StentParameters(
        stent_french=6.0,
        stent_length=150,
        n_prox=2,
        n_mid=5,
        n_dist=2,
        r_t=0.15,
        r_sh=0.5,
        unroofed_length=10.0
    )
    
    gen = StentGenerator(params)
    solid = gen.generate()
    
    out_path = Path("data/cad_exports/test_stent.step")
    gen.export_step(out_path)
    print(f"Exported to {out_path}")
    print(gen.get_info())
