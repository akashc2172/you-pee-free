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
from typing import Dict, List, Literal, Optional
import math

from src.cad.mesh_quality import validate_stl


STL_QUALITY_PROFILES: Dict[str, Dict[str, float]] = {
    "draft": {"tolerance": 0.005, "angular_tolerance": 0.25},
    "standard": {"tolerance": 0.001, "angular_tolerance": 0.1},
    "high": {"tolerance": 0.0005, "angular_tolerance": 0.05},
}


@dataclass
class StlExportOptions:
    """STL export/QA options."""

    tolerance: float = 0.001
    angular_tolerance: float = 0.1
    ascii_format: bool = False
    validate_mesh: bool = True
    quality_profile: Literal["draft", "standard", "high"] = "standard"

    @classmethod
    def from_profile(
        cls,
        quality_profile: Literal["draft", "standard", "high"] = "standard",
        ascii_format: bool = False,
        validate_mesh: bool = True,
    ) -> "StlExportOptions":
        if quality_profile not in STL_QUALITY_PROFILES:
            raise ValueError(f"Unknown STL quality profile: {quality_profile}")
        profile = STL_QUALITY_PROFILES[quality_profile]
        return cls(
            tolerance=profile["tolerance"],
            angular_tolerance=profile["angular_tolerance"],
            ascii_format=ascii_format,
            validate_mesh=validate_mesh,
            quality_profile=quality_profile,
        )


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
        
        # Precompute requested and realized hole positions along body
        self._compute_and_finalize_holes()
    
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
    
    def _compute_section_positions(self, start: float, end: float, n_holes: int) -> List[float]:
        """Compute evenly spaced positions within a section interval."""
        if n_holes <= 0:
            return []
        if n_holes == 1:
            return [(start + end) / 2.0]
        spacing = (end - start) / (n_holes - 1)
        return [start + i * spacing for i in range(n_holes)]

    def _compute_requested_hole_positions(self) -> Dict[str, List[float]]:
        """Compute requested section-wise hole positions."""
        buffer = max(self.BUFFER_MIN, self.hole_radius)

        prox_start = buffer
        prox_end = self.section_length_prox - buffer

        mid_start = self.section_length_prox + buffer
        mid_end = self.section_length_prox + self.section_length_mid - buffer

        dist_start = self.section_length_prox + self.section_length_mid + buffer
        dist_end = self.stent_length - buffer

        return {
            "prox": self._compute_section_positions(prox_start, prox_end, self.n_prox),
            "mid": self._compute_section_positions(mid_start, mid_end, self.n_mid),
            "dist": self._compute_section_positions(dist_start, dist_end, self.n_dist),
        }

    def _compute_and_finalize_holes(self):
        """Compute requested and realized hole maps with unroof-aware distal rebalance."""
        requested = self._compute_requested_hole_positions()
        realized = {
            "prox": list(requested["prox"]),
            "mid": list(requested["mid"]),
            "dist": list(requested["dist"]),
        }

        self.requested_n_prox = self.n_prox
        self.requested_n_mid = self.n_mid
        self.requested_n_dist = self.n_dist
        self.requested_body_holes = self.n_prox + self.n_mid + self.n_dist

        self.suppressed_holes_due_to_unroofed = 0
        self.suppressed_holes_due_to_clearance = 0

        # Distal overlap policy: auto-rebalance into legal distal interval.
        if self.unroofed_length > 0 and self.n_dist > 0:
            hole_clearance = max(self.BUFFER_MIN, self.hole_radius)
            unroof_start = self.stent_length - self.unroofed_length

            distal_positions = requested["dist"]
            kept = []
            for pos in distal_positions:
                if pos >= unroof_start:
                    self.suppressed_holes_due_to_unroofed += 1
                elif pos >= unroof_start - hole_clearance:
                    self.suppressed_holes_due_to_clearance += 1
                else:
                    kept.append(pos)

            dist_start = self.section_length_prox + self.section_length_mid + hole_clearance
            legal_end = min(self.stent_length - hole_clearance, unroof_start - hole_clearance)

            if legal_end > dist_start:
                pitch_min = self.d_sh + self.GAP_MIN
                legal_len = legal_end - dist_start
                max_fit = int(legal_len / pitch_min) + 1
                target_count = min(self.n_dist, max_fit)
                realized["dist"] = self._compute_section_positions(dist_start, legal_end, target_count)
            else:
                realized["dist"] = []

        self.requested_hole_positions_by_section = requested
        self.realized_hole_positions_by_section = realized
        self.requested_hole_positions = requested["prox"] + requested["mid"] + requested["dist"]
        self.realized_hole_positions = realized["prox"] + realized["mid"] + realized["dist"]

        self.realized_n_prox = len(realized["prox"])
        self.realized_n_mid = len(realized["mid"])
        self.realized_n_dist = len(realized["dist"])
        self.realized_body_holes = self.realized_n_prox + self.realized_n_mid + self.realized_n_dist

        # Backward-compatible aliases for downstream callers.
        self.hole_positions = self.realized_hole_positions


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
        p.coil_holes_requested = len(p.coil_hole_params) * int(p.turns_prox > 0) + len(p.coil_hole_params) * int(p.turns_dist > 0)
        p.coil_holes_realized = 0
        
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
            hollow, n_ok = self._cut_coil_holes(hollow, prox_wire)
            p.coil_holes_realized += n_ok
        if dist_wire:
            hollow, n_ok = self._cut_coil_holes(hollow, dist_wire)
            p.coil_holes_realized += n_ok
        
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
        """Cut side holes along the body at realized positions."""
        p = self.params
        axis = axis.normalized()
        
        # Compute perpendicular directions for alternating hole placement
        arb = Vector(1, 0, 0) if abs(axis.X) < 0.9 else Vector(0, 1, 0)
        v1 = axis.cross(arb).normalized()
        v2 = axis.cross(v1).normalized()
        
        with BuildPart() as bp:
            add(solid)
            for i, d in enumerate(p.realized_hole_positions):
                center = start_pt + (axis * d)
                cut_dir = v1 if i % 2 == 0 else v2
                with BuildSketch(Plane(origin=center, z_dir=cut_dir)):
                    Circle(radius=p.hole_radius)
                # Bidirectional cut through the entire tube to prevent non-manifold edges
                extrude(amount=p.r_outer * 4, both=True, mode=Mode.SUBTRACT)
        return bp.part
    
    def _cut_coil_holes(self, solid: Part, wire: Wire) -> tuple[Part, int]:
        """Cut holes at specified t-parameters along a coil wire."""
        p = self.params
        result = solid
        n_success = 0
        
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
                n_success += 1
            except Exception:
                pass  # Skip if location fails
        return result, n_success
    
    def export_step(self, path: Path):
        """Export to STEP format (for COMSOL import)."""
        if self._solid is None:
            self.generate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_step(self._solid, str(path))
    
    def export_stl(self, path: Path, options: Optional[StlExportOptions] = None) -> dict:
        """Export to STL format with explicit tessellation controls and optional QA."""
        if self._solid is None:
            self.generate()

        options = options or StlExportOptions.from_profile("standard")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_stl(
            self._solid,
            str(path),
            tolerance=options.tolerance,
            angular_tolerance=options.angular_tolerance,
            ascii_format=options.ascii_format,
        )

        qa = None
        if options.validate_mesh:
            qa_report = validate_stl(path)
            qa = qa_report.to_dict()
            if not qa_report.passed:
                raise ValueError(
                    f"STL QA failed for {path}: {', '.join(qa_report.fail_reasons)}"
                )

        return {
            "path": str(path),
            "profile": options.quality_profile,
            "tolerance": options.tolerance,
            "angular_tolerance": options.angular_tolerance,
            "ascii": options.ascii_format,
            "filesize_bytes": path.stat().st_size,
            "qa": qa,
        }
    
    def get_info(self) -> dict:
        """Return summary of stent geometry."""
        p = self.params
        requested_total = p.requested_body_holes
        realized_total = p.realized_body_holes
        coil_requested = getattr(p, "coil_holes_requested", 0)
        coil_realized = getattr(p, "coil_holes_realized", 0)
        return {
            "French": p.stent_french,
            "OD (mm)": round(p.OD, 3),
            "ID (mm)": round(p.ID, 3),
            "Wall (mm)": round(p.wall_thickness, 3),
            "Body Length (mm)": p.stent_length,
            "Total Holes": realized_total,  # Deprecated legacy key: realized body holes.
            "Requested Body Holes": requested_total,
            "Realized Body Holes": realized_total,
            "Requested n_prox/n_mid/n_dist": [p.requested_n_prox, p.requested_n_mid, p.requested_n_dist],
            "Realized n_prox/n_mid/n_dist": [p.realized_n_prox, p.realized_n_mid, p.realized_n_dist],
            "Suppressed Holes (Unroofed)": p.suppressed_holes_due_to_unroofed,
            "Suppressed Holes (Clearance)": p.suppressed_holes_due_to_clearance,
            "Coil Holes Requested": coil_requested,
            "Coil Holes Realized": coil_realized,
            "Requested Hole Positions": [round(x, 1) for x in p.requested_hole_positions],
            "Realized Hole Positions": [round(x, 1) for x in p.realized_hole_positions],
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
