"""
Stent CAD Generator using build123d.

This module provides the StentGenerator class for creating parametric stent
geometries with:
- Proximal and distal helical coils (fixed geometry by default)
- Hollow tube body with configurable wall thickness
- Side holes in proximal, middle, and distal sections
- Unroofed (half-pipe) distal section option
- Coil holes for drainage at pigtail ends

Validated for COMSOL CFD import via STEP export.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Literal, Optional, Tuple

from build123d import *

from src.cad.mesh_quality import validate_stl
from src.measurement_surfaces.schema import (
    MeasurementFeature,
    MeasurementSurfacePackage,
    validate_measurement_surface_metadata,
)

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
    stent_french: float = 6.0  # French size (1 Fr = 0.333 mm)
    stent_length: float = 150.0  # Total body length (mm)

    # Coil geometry controls are intentionally locked for v1 campaign stability.
    # They remain as fields for compatibility with older rows/scripts, but are
    # overwritten by fixed constants when freeze_coil_geometry is true.
    coil_R_prox: float = 6.0
    pitch_prox: float = 6.0
    turns_prox: float = 1.5
    coil_R_dist: float = 6.0
    pitch_dist: float = 6.0
    turns_dist: float = 1.5

    # Freeze coil geometry by default for early campaign stability.
    freeze_coil_geometry: bool = True

    # Fraction-based parameters (sampled 0-1, then derived)
    r_t: float = 0.15  # Wall thickness = r_t * OD
    r_sh: float = 0.50  # Side hole diameter = r_sh * ID (capped)
    r_end: float = 0.70  # End hole diameter = r_end * ID (capped)

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
    GAP_MIN: float = 0.3  # Minimum gap between holes (mm)
    BUFFER_MIN: float = 1.0  # Buffer from section ends (mm)
    CAP_MARGIN: float = 0.15  # d_sh <= ID - cap_margin (mm)
    ID_MIN: float = 0.6  # Minimum inner diameter (mm)
    FIXED_COIL_R: ClassVar[float] = 6.0
    FIXED_PITCH: ClassVar[float] = 6.0
    FIXED_TURNS: ClassVar[float] = 1.5

    # Export-frame metadata populated after geometry generation/canonicalization.
    export_body_start: Optional[Vector] = None
    export_body_end: Optional[Vector] = None
    export_body_axis: Optional[Vector] = None
    export_body_center_start: Optional[Vector] = None
    export_body_center_end: Optional[Vector] = None
    export_body_center_y: Optional[float] = None
    export_body_center_z: Optional[float] = None
    export_body_start_x: Optional[float] = None
    export_body_end_x: Optional[float] = None
    export_bbox_min_x: Optional[float] = None
    export_bbox_max_x: Optional[float] = None
    export_bbox_min: Optional[Vector] = None
    export_bbox_max: Optional[Vector] = None
    distal_partition_margin_mm: Optional[float] = None
    distal_partition_min_x_body_mm: Optional[float] = None
    distal_partition_max_x_body_mm: Optional[float] = None
    distal_partition_x_body_mm: Optional[float] = None
    feasibility_warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Ensure integers for hole counts
        self.n_prox = int(self.n_prox)
        self.n_mid = int(self.n_mid)
        self.n_dist = int(self.n_dist)

        self._apply_fixed_coil_geometry()
        self._derive_and_validate()

    def _apply_fixed_coil_geometry(self):
        """Pin coil geometry to fixed values unless explicitly unfrozen."""
        if not self.freeze_coil_geometry:
            return
        self.coil_R_prox = self.FIXED_COIL_R
        self.pitch_prox = self.FIXED_PITCH
        self.turns_prox = self.FIXED_TURNS
        self.coil_R_dist = self.FIXED_COIL_R
        self.pitch_dist = self.FIXED_PITCH
        self.turns_dist = self.FIXED_TURNS

    def _derive_and_validate(self):
        """Derive absolute dimensions and validate geometry."""
        self.feasibility_warnings = []

        # Derive from French size
        self.OD = 0.333 * self.stent_french
        self.wall_thickness = self.r_t * self.OD
        self.ID = self.OD - 2 * self.wall_thickness

        # Check minimum lumen
        if self.ID < self.ID_MIN:
            raise ValueError(
                f"ID ({self.ID:.2f}) < ID_MIN ({self.ID_MIN}). Reduce r_t or increase French."
            )

        # Derive hole diameters (capped)
        self.d_sh = min(self.r_sh * self.ID, self.ID - self.CAP_MARGIN)
        self.d_end = min(self.r_end * self.ID, self.ID - self.CAP_MARGIN)

        # Derive radii for CAD
        self.r_outer = self.OD / 2
        self.r_inner = self.ID / 2
        self.hole_radius = self.d_sh / 2
        # Coil-hole radius is fixed in v1 to match body-hole radius.
        self.coil_hole_radius = self.hole_radius

        # Derive middle section length
        self.section_length_mid = (
            self.stent_length - self.section_length_prox - self.section_length_dist
        )
        if self.section_length_mid < 10.0:
            raise ValueError(
                f"Middle section ({self.section_length_mid:.1f}mm) < 10mm. Reduce prox/dist sections."
            )

        # Validate hole packing in each section
        self._validate_hole_packing("prox", self.section_length_prox, self.n_prox)
        self._validate_hole_packing("mid", self.section_length_mid, self.n_mid)
        self._validate_hole_packing("dist", self.section_length_dist, self.n_dist)

        # Precompute requested and realized hole positions along body
        self._compute_and_finalize_holes()
        self._validate_distal_partition_feasibility()

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
                realized["dist"] = self._compute_section_positions(
                    dist_start, legal_end, target_count
                )
            else:
                realized["dist"] = []

        self.requested_hole_positions_by_section = requested
        self.realized_hole_positions_by_section = realized
        self.requested_hole_positions = requested["prox"] + requested["mid"] + requested["dist"]
        self.realized_hole_positions = realized["prox"] + realized["mid"] + realized["dist"]

        self.realized_n_prox = len(realized["prox"])
        self.realized_n_mid = len(realized["mid"])
        self.realized_n_dist = len(realized["dist"])
        self.requested_midsection_hole_count = self.requested_n_mid
        self.realized_midsection_hole_count = self.realized_n_mid
        self.realized_body_holes = self.realized_n_prox + self.realized_n_mid + self.realized_n_dist
        self.realized_body_hole_total_area = (
            math.pi * (self.hole_radius**2) * self.realized_body_holes
        )

        sorted_realized = sorted(self.realized_hole_positions)
        if len(sorted_realized) >= 2:
            spacings = [b - a for a, b in zip(sorted_realized[:-1], sorted_realized[1:])]
            self.realized_body_hole_min_spacing = min(spacings)
            self.realized_body_hole_mean_spacing = sum(spacings) / len(spacings)
            self.realized_nearest_neighbor_spacing = self.realized_body_hole_min_spacing
        else:
            self.realized_body_hole_min_spacing = None
            self.realized_body_hole_mean_spacing = None
            self.realized_nearest_neighbor_spacing = None

        # Body holes alternate between two orthogonal angular cuts.
        self.realized_arc_positions = [
            0.0 if i % 2 == 0 else 90.0 for i in range(self.realized_body_holes)
        ]

        # Backward-compatible aliases for downstream callers.
        self.hole_positions = self.realized_hole_positions

    def _validate_distal_partition_feasibility(self):
        """Ensure the distal partition plane can sit inside the distal body and upstream of any unroof."""
        partition_margin = max(float(self.BUFFER_MIN), float(self.r_outer))
        distal_section_start = float(self.section_length_prox + self.section_length_mid)
        safe_min_x = distal_section_start + partition_margin
        safe_max_x = float(self.stent_length) - partition_margin
        if self.unroofed_length > 0:
            safe_max_x = min(
                safe_max_x,
                float(self.stent_length) - float(self.unroofed_length) - partition_margin,
            )

        self.distal_partition_margin_mm = partition_margin
        self.distal_partition_min_x_body_mm = safe_min_x
        self.distal_partition_max_x_body_mm = safe_max_x

        if safe_max_x <= safe_min_x:
            raise ValueError(
                "Distal partition plane infeasible. "
                "Reduce unroofed_length or leave more distal body length upstream of the unroof."
            )

        self.distal_partition_x_body_mm = safe_max_x
        if (safe_max_x - safe_min_x) <= partition_margin:
            self.feasibility_warnings.append("tight_distal_partition_window")


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
        p.coil_holes_requested = len(p.coil_hole_params) * int(p.turns_prox > 0) + len(
            p.coil_hole_params
        ) * int(p.turns_dist > 0)
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

        # 6. Cut holes — capture exact pre-canonical hole centers/normals for sidecar metadata.
        hollow, raw_hole_entries = self._cut_body_holes(hollow, body_start_pt, body_start_tan)
        if prox_wire:
            hollow, n_ok, prox_entries = self._cut_coil_holes(hollow, prox_wire, region="prox")
            p.coil_holes_realized += n_ok
            raw_hole_entries.extend(prox_entries)
        if dist_wire:
            hollow, n_ok, dist_entries = self._cut_coil_holes(hollow, dist_wire, region="dist")
            p.coil_holes_realized += n_ok
            raw_hole_entries.extend(dist_entries)
        p._raw_hole_entries = raw_hole_entries

        p.requested_coil_hole_count = p.coil_holes_requested
        p.realized_coil_hole_count = p.coil_holes_realized
        p.requested_total_hole_count = p.requested_body_holes + p.requested_coil_hole_count
        p.realized_total_hole_count = p.realized_body_holes + p.realized_coil_hole_count
        p.realized_total_hole_area = math.pi * (p.hole_radius**2) * p.realized_total_hole_count

        # Normalize all exported solids into one global frame so downstream
        # COMSOL envelopes and coordinate boxes can assume a stable orientation.
        hollow = self._canonicalize_export_frame(
            hollow,
            body_start_pt=body_start_pt,
            body_end_pt=body_end_pt,
            prox_wire=prox_wire,
        )

        self._solid = hollow
        return hollow

    @staticmethod
    def _project_orthogonal(vector: Vector, axis: Vector) -> Vector:
        """Remove the component of vector along axis."""
        return vector - axis * vector.dot(axis)

    def _stable_reference_normal(
        self,
        body_start_pt: Vector,
        body_axis: Vector,
        prox_wire: Optional[Wire],
    ) -> Vector:
        """Pick a repeatable perpendicular reference to fix roll about the shaft axis."""
        candidates = []
        if prox_wire:
            candidates.append(prox_wire.edges()[0].start_point() - body_start_pt)
        candidates.extend([Vector(0, 0, 1), Vector(0, 1, 0)])

        for candidate in candidates:
            projected = self._project_orthogonal(candidate, body_axis)
            if projected.length > 1e-6:
                return projected.normalized()
        raise ValueError("Unable to determine a stable canonical export normal")

    def _canonicalize_export_frame(
        self,
        solid: Part,
        body_start_pt: Vector,
        body_end_pt: Vector,
        prox_wire: Optional[Wire],
    ) -> Part:
        """Align the straight body shaft to +X and anchor its centerline at the origin."""

        def _snap(value: float) -> float:
            return 0.0 if abs(value) < 1e-9 else float(value)

        def _snap_vector(vector: Vector) -> Vector:
            return Vector(_snap(vector.X), _snap(vector.Y), _snap(vector.Z))

        def _transform_pt(raw: Vector) -> Vector:
            """Apply the same rigid transform used for the solid to any raw point."""
            aligned = target_plane.from_local_coords(src_plane.to_local_coords(raw))
            return aligned + shift + Vector(0, -measured_center_y, -measured_center_z)

        def _transform_dir(raw: Vector) -> Vector:
            """Apply the rotational part of the canonical transform to any raw direction."""
            transformed_origin = target_plane.from_local_coords(src_plane.to_local_coords(body_start_pt))
            transformed_tip = target_plane.from_local_coords(
                src_plane.to_local_coords(body_start_pt + raw)
            )
            direction = transformed_tip - transformed_origin
            return direction.normalized()

        p = self.params
        body_axis = (body_end_pt - body_start_pt).normalized()
        reference_normal = self._stable_reference_normal(body_start_pt, body_axis, prox_wire)

        src_plane = Plane(origin=body_start_pt, x_dir=body_axis, z_dir=reference_normal)
        target_plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
        alignment = target_plane.location * src_plane.location.inverse()

        canonical = solid.moved(alignment)
        export_body_start = target_plane.from_local_coords(src_plane.to_local_coords(body_start_pt))
        export_body_end = target_plane.from_local_coords(src_plane.to_local_coords(body_end_pt))

        # Anchor the straight-body centerline, not the whole-solid bounding box.
        shift = Vector(-export_body_start.X, -export_body_start.Y, -export_body_start.Z)
        canonical = canonical.moved(Location(shift))
        measured_centers = self._measure_body_cross_section_centers(canonical)
        measured_center_y = sum(center.Y for center in measured_centers) / len(measured_centers)
        measured_center_z = sum(center.Z for center in measured_centers) / len(measured_centers)
        canonical = canonical.moved(Location(Vector(0, -measured_center_y, -measured_center_z)))
        bbox = canonical.bounding_box()

        corrected_body_start = _snap_vector(
            export_body_start + shift + Vector(0, -measured_center_y, -measured_center_z)
        )
        corrected_body_end = _snap_vector(
            export_body_end + shift + Vector(0, -measured_center_y, -measured_center_z)
        )
        p.export_body_start = corrected_body_start
        p.export_body_end = corrected_body_end
        p.export_body_center_start = Vector(0.0, 0.0, 0.0)
        p.export_body_center_end = Vector(
            _snap(corrected_body_end.X - corrected_body_start.X), 0.0, 0.0
        )
        p.export_body_axis = _snap_vector(
            (p.export_body_center_end - p.export_body_center_start).normalized()
        )
        p.export_body_center_y = 0.0
        p.export_body_center_z = 0.0
        p.export_body_start_x = 0.0
        p.export_body_end_x = _snap(p.export_body_center_end.X)
        p.export_bbox_min = _snap_vector(bbox.min)
        p.export_bbox_max = _snap_vector(bbox.max)
        p.export_bbox_min_x = _snap(bbox.min.X)
        p.export_bbox_max_x = _snap(bbox.max.X)

        export_hole_entries: List[dict] = []
        for raw_entry in getattr(p, "_raw_hole_entries", []):
            center_vec = _snap_vector(_transform_pt(raw_entry["center_raw"]))
            normal_vec = _snap_vector(_transform_dir(raw_entry["normal_raw"]))
            export_hole_entries.append(
                {
                    "hole_id": raw_entry["hole_id"],
                    "region": raw_entry["region"],
                    "type": raw_entry["type"],
                    "center_vec": center_vec,
                    "normal_vec": normal_vec,
                    "radius_mm": float(raw_entry["radius_mm"]),
                    "arc_deg": raw_entry.get("arc_deg"),
                    "axial_x_mm": float(center_vec.X),
                }
            )
        p.export_hole_entries = export_hole_entries

        return canonical

    @staticmethod
    def _vector_to_list(vector: Vector) -> List[float]:
        return [float(vector.X), float(vector.Y), float(vector.Z)]

    def _compute_distal_partition_plane_x_mm(self) -> float:
        """Return the canonical-frame distal partition section location."""
        p = self.params
        if p.export_body_start_x is None or p.export_body_end_x is None:
            raise RuntimeError("Export-frame body extents are not available for distal partition placement")

        partition_margin = max(float(p.BUFFER_MIN), float(p.r_outer))
        distal_section_start_x = float(p.export_body_start_x) + float(p.section_length_prox + p.section_length_mid)
        safe_min_x = distal_section_start_x + partition_margin
        safe_max_x = float(p.export_body_end_x) - partition_margin
        if p.unroofed_length > 0:
            safe_max_x = min(
                safe_max_x,
                float(p.export_body_end_x) - float(p.unroofed_length) - partition_margin,
            )
        if safe_max_x <= safe_min_x:
            raise RuntimeError(
                "Distal partition plane became infeasible after canonicalization; "
                "the unroof leaves no valid distal cross-section window"
            )
        return safe_max_x

    def _build_selection_boxes(self, hole_entries: List[dict], selection_margin_mm: float) -> Dict[str, dict]:
        """Build metadata-derived helper boxes for combined and typed regional selections."""
        p = self.params
        combined_boxes: Dict[str, Optional[dict]] = {}
        typed_boxes: Dict[str, Dict[str, Optional[dict]]] = {}

        def _box_for(entries: List[dict]) -> Optional[dict]:
            if not entries:
                return None

            xs = [float(entry["axial_x_mm"]) for entry in entries]
            ys = [float(entry["center_vec"].Y) for entry in entries]
            zs = [float(entry["center_vec"].Z) for entry in entries]
            x_margin = max(float(entry["radius_mm"]) for entry in entries) + selection_margin_mm
            radial_padding = p.r_outer + selection_margin_mm
            y_pad = max(abs(value) for value in ys) + radial_padding
            z_pad = max(abs(value) for value in zs) + radial_padding

            return {
                "x_min_mm": round(min(xs) - x_margin, 6),
                "x_max_mm": round(max(xs) + x_margin, 6),
                "y_min_mm": round(-y_pad, 6),
                "y_max_mm": round(y_pad, 6),
                "z_min_mm": round(-z_pad, 6),
                "z_max_mm": round(z_pad, 6),
                "n_holes": len(entries),
                "hole_ids": [entry["hole_id"] for entry in entries],
            }

        for region in ("prox", "mid", "dist"):
            region_entries = [entry for entry in hole_entries if entry["region"] == region]
            shaft_entries = [entry for entry in region_entries if entry["type"] == "shaft"]
            coil_entries = [entry for entry in region_entries if entry["type"] == "coil"]
            combined_boxes[region] = _box_for(region_entries)
            typed_boxes[region] = {
                "combined": _box_for(region_entries),
                "shaft": _box_for(shaft_entries),
                "coil": _box_for(coil_entries),
            }
        return {
            "region_selection_boxes": combined_boxes,
            "typed_region_selection_boxes": typed_boxes,
        }

    def _validate_export_hole_entries(
        self,
        hole_entries: List[dict],
        tolerance_mm: float = 0.1,
    ) -> None:
        """Fail loudly if metadata drifts from the realized generator geometry."""
        p = self.params
        if not hole_entries:
            return

        if len(hole_entries) != getattr(p, "realized_total_hole_count", len(hole_entries)):
            raise ValueError("hole_metadata_count_mismatch")

        shaft_expected = {
            "prox": list(p.realized_hole_positions_by_section["prox"]),
            "mid": list(p.realized_hole_positions_by_section["mid"]),
            "dist": list(p.realized_hole_positions_by_section["dist"]),
        }
        shaft_actual: Dict[str, List[dict]] = {"prox": [], "mid": [], "dist": []}
        for entry in hole_entries:
            center = entry["center_vec"]
            normal = entry["normal_vec"]
            norm_mag = math.sqrt(normal.X**2 + normal.Y**2 + normal.Z**2)
            if abs(norm_mag - 1.0) > 1e-6:
                raise ValueError(f"hole_normal_not_unit: {entry['hole_id']}")
            if center.X < p.export_bbox_min_x - tolerance_mm or center.X > p.export_bbox_max_x + tolerance_mm:
                raise ValueError(f"hole_center_outside_bbox: {entry['hole_id']}")
            if abs(float(entry["axial_x_mm"]) - float(center.X)) > tolerance_mm:
                raise ValueError(f"hole_axial_x_mismatch: {entry['hole_id']}")
            if entry["type"] == "shaft":
                shaft_actual[entry["region"]].append(entry)
                if max(abs(center.Y), abs(center.Z)) > tolerance_mm:
                    raise ValueError(f"shaft_hole_off_centerline: {entry['hole_id']}")

        for region, expected_positions in shaft_expected.items():
            actual_entries = sorted(shaft_actual[region], key=lambda entry: entry["axial_x_mm"])
            if len(actual_entries) != len(expected_positions):
                raise ValueError(f"shaft_hole_count_mismatch:{region}")
            for expected_x, entry in zip(expected_positions, actual_entries):
                if abs(float(entry["axial_x_mm"]) - float(expected_x)) > tolerance_mm:
                    raise ValueError(f"shaft_hole_position_mismatch:{entry['hole_id']}")

    def _body_cross_section_sample_positions(self) -> List[float]:
        """Choose body x-positions away from ends and hole centers for centroid checks."""
        p = self.params
        margin = max(p.r_outer * 2.0, p.BUFFER_MIN)
        hole_clearance = max(p.hole_radius * 2.5, p.BUFFER_MIN)
        candidates = [p.stent_length * frac for frac in (0.2, 0.35, 0.5, 0.65, 0.8)]
        safe_positions = []

        for x_pos in candidates:
            if x_pos <= margin or x_pos >= p.stent_length - margin:
                continue
            if any(
                abs(x_pos - hole_pos) <= hole_clearance for hole_pos in p.realized_hole_positions
            ):
                continue
            safe_positions.append(x_pos)

        if safe_positions:
            return safe_positions[:3]

        boundaries = [margin]
        boundaries.extend(
            hole_pos
            for hole_pos in sorted(p.realized_hole_positions)
            if margin < hole_pos < p.stent_length - margin
        )
        boundaries.append(p.stent_length - margin)

        for left, right in zip(boundaries[:-1], boundaries[1:]):
            if right - left <= 2 * hole_clearance:
                continue
            safe_positions.append((left + right) / 2.0)

        if safe_positions:
            return safe_positions[:3]

        midpoint = min(max(p.stent_length / 2.0, margin), p.stent_length - margin)
        return [midpoint]

    def _measure_body_cross_section_centers(self, solid: Part) -> List[Vector]:
        """Measure actual shaft cross-section centroids from the final solid."""
        centers: List[Vector] = []
        for x_pos in self._body_cross_section_sample_positions():
            section = solid.intersect(Plane(origin=(x_pos, 0, 0), z_dir=(1, 0, 0)))
            centers.append(section.center(CenterOf.MASS))
        return centers

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

        # Fix distal-coil roll explicitly. Using Plane(..., z_dir=...) alone leaves
        # the rotation about the tangent underconstrained, which can place the
        # distal pigtail phase inconsistently relative to the shaft.
        source_x_dir = self._project_orthogonal(Vector(1, 0, 0), hs_tan)
        if source_x_dir.length <= 1e-6:
            source_x_dir = self._project_orthogonal(Vector(0, 1, 0), hs_tan)
        source_x_dir = source_x_dir.normalized()

        target_x_dir = self._project_orthogonal(Vector(0, 0, 1), body_end_tan)
        if target_x_dir.length <= 1e-6:
            target_x_dir = self._project_orthogonal(Vector(0, 1, 0), body_end_tan)
        target_x_dir = target_x_dir.normalized()

        pl_src = Plane(origin=hs_pt, x_dir=source_x_dir, z_dir=hs_tan)
        pl_target = Plane(origin=body_end_pt, x_dir=target_x_dir, z_dir=body_end_tan)
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

    def _build_body_hole_entries(self, start_pt: Vector, axis: Vector) -> List[dict]:
        """Build raw body-hole entries from the exact cut centers and normals."""
        p = self.params
        axis = axis.normalized()

        # Compute perpendicular directions for alternating hole placement.
        arb = Vector(1, 0, 0) if abs(axis.X) < 0.9 else Vector(0, 1, 0)
        v1 = axis.cross(arb).normalized()
        v2 = axis.cross(v1).normalized()

        entries: List[dict] = []
        global_idx = 0
        for region in ("prox", "mid", "dist"):
            for local_idx, axial_x in enumerate(p.realized_hole_positions_by_section[region]):
                center = start_pt + (axis * axial_x)
                cut_dir = v1 if global_idx % 2 == 0 else v2
                arc_positions = getattr(p, "realized_arc_positions", [])
                arc_deg = arc_positions[global_idx] if global_idx < len(arc_positions) else 0.0
                entries.append(
                    {
                        "hole_id": f"shaft_{region}_{local_idx:03d}",
                        "region": region,
                        "type": "shaft",
                        "center_raw": center,
                        "normal_raw": cut_dir.normalized(),
                        "radius_mm": p.hole_radius,
                        "arc_deg": arc_deg,
                        "axial_x_mm": float(axial_x),
                    }
                )
                global_idx += 1
        return entries

    def _cut_body_holes(
        self,
        solid: Part,
        start_pt: Vector,
        axis: Vector,
    ) -> Tuple[Part, List[dict]]:
        """Cut side holes along the body and return raw metadata entries."""
        entries = self._build_body_hole_entries(start_pt, axis)

        with BuildPart() as bp:
            add(solid)
            for entry in entries:
                with BuildSketch(Plane(origin=entry["center_raw"], z_dir=entry["normal_raw"])):
                    Circle(radius=self.params.hole_radius)
                # Single-direction cut creates a one-wall side hole instead of a through-hole.
                extrude(amount=self.params.r_outer * 4, both=False, mode=Mode.SUBTRACT)
        return bp.part, entries

    def _cut_coil_holes(self, solid: Part, wire: Wire, region: str) -> Tuple[Part, int, List[dict]]:
        """Cut holes at specified t-parameters along a coil wire.

        Returns (solid, n_success, raw_entries) where raw_entries store the
        exact pre-canonical cut centers and normals for each realized coil hole.
        """
        p = self.params
        result = solid
        n_success = 0
        raw_entries: List[dict] = []

        for raw_idx, t_val in enumerate(p.coil_hole_params):
            try:
                loc = wire.location_at(t_val)
                cut_normal = loc.x_axis.direction.normalized()
                cut_plane = Plane(origin=loc.position, z_dir=cut_normal)
                with BuildPart() as bp:
                    add(result)
                    with BuildSketch(cut_plane):
                        Circle(radius=p.coil_hole_radius)
                    extrude(amount=p.r_outer * 3, both=False, mode=Mode.SUBTRACT)
                result = bp.part
                raw_entries.append(
                    {
                        "hole_id": f"coil_{region}_{raw_idx:03d}",
                        "region": region,
                        "type": "coil",
                        "center_raw": loc.position,
                        "normal_raw": cut_normal,
                        "radius_mm": p.coil_hole_radius,
                        "arc_deg": None,
                        "axial_x_mm": None,
                    }
                )
                n_success += 1
            except Exception:
                pass  # Skip if location fails.
        return result, n_success, raw_entries

    def export_step(self, path: Path):
        """Export to STEP format and emit the matching hole-metadata sidecar."""
        if self._solid is None:
            self.generate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        export_step(self._solid, str(path))
        self.export_hole_metadata(path.with_suffix(".holes.json"), design_id=path.stem)
        self.export_measurement_surface_metadata(path.with_suffix(".meters.json"), design_id=path.stem)

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
                raise ValueError(f"STL QA failed for {path}: {', '.join(qa_report.fail_reasons)}")

        return {
            "path": str(path),
            "profile": options.quality_profile,
            "tolerance": options.tolerance,
            "angular_tolerance": options.angular_tolerance,
            "ascii": options.ascii_format,
            "filesize_bytes": path.stat().st_size,
            "qa": qa,
        }

    # ------------------------------------------------------------------
    # Hole metadata sidecar
    # ------------------------------------------------------------------

    def get_hole_metadata(
        self,
        design_id: Optional[str] = None,
        validation_tolerance_mm: float = 0.1,
    ) -> dict:
        """Return metadata-driven hole selection/analysis data in the canonical export frame."""
        if self._solid is None:
            raise RuntimeError(
                "Call generate() (or export_step / export_stl) before get_hole_metadata()."
            )

        p = self.params
        selection_margin_mm = 0.15
        hole_entries = list(getattr(p, "export_hole_entries", []))
        self._validate_export_hole_entries(hole_entries, tolerance_mm=validation_tolerance_mm)

        sorted_entries = sorted(
            hole_entries,
            key=lambda entry: (
                round(float(entry["axial_x_mm"]), 9),
                0 if entry["type"] == "shaft" else 1,
                entry["hole_id"],
            ),
        )

        holes: List[dict] = []
        axial_order: List[dict] = []
        for axial_rank, entry in enumerate(sorted_entries):
            center = entry["center_vec"]
            normal = entry["normal_vec"]
            sphere_radius = entry["radius_mm"] + selection_margin_mm
            slab_half_width = entry["radius_mm"] + selection_margin_mm
            hole_record = {
                "hole_id": entry["hole_id"],
                "id": entry["hole_id"],
                "region": entry["region"],
                "type": entry["type"],
                "center_mm": [round(value, 6) for value in self._vector_to_list(center)],
                "center": [round(value, 6) for value in self._vector_to_list(center)],
                "radius_mm": round(float(entry["radius_mm"]), 6),
                "hole_radius": round(float(entry["radius_mm"]), 6),
                "normal": [round(value, 9) for value in self._vector_to_list(normal)],
                "normal_vector": [round(value, 9) for value in self._vector_to_list(normal)],
                "axial_x_mm": round(float(entry["axial_x_mm"]), 6),
                "axial_rank": axial_rank,
                "arc_deg": entry.get("arc_deg"),
                "selection_sphere_radius_mm": round(sphere_radius, 6),
                "selection_sphere_radius": round(sphere_radius, 6),
                "selection_cylinder_radius_mm": round(sphere_radius, 6),
                "slab_half_width_x_mm": round(slab_half_width, 6),
                "slab_half_width_x": round(slab_half_width, 6),
            }
            holes.append(hole_record)
            axial_order.append(
                {
                    "hole_id": hole_record["hole_id"],
                    "axial_x_mm": hole_record["axial_x_mm"],
                    "axial_rank": hole_record["axial_rank"],
                    "region": hole_record["region"],
                    "type": hole_record["type"],
                }
            )

        selection_boxes = self._build_selection_boxes(sorted_entries, selection_margin_mm)
        inferred_design_id = design_id or getattr(p, "design_id", None) or "unknown_design"

        return {
            "schema_version": "hole_metadata_sidecar_v2",
            "design_id": inferred_design_id,
            "frame_definition": {
                "name": "canonical_stent_export_frame",
                "body_axis": "+X",
                "body_axis_vector": [1.0, 0.0, 0.0],
                "body_start_at_x_mm": 0.0,
                "units": "mm",
                "description": "Rigid canonical export frame shared by STEP geometry and hole metadata.",
            },
            "stent_length_mm": round(p.stent_length, 6),
            "od_mm": round(p.OD, 6),
            "id_mm": round(p.ID, 6),
            "r_outer_mm": round(p.r_outer, 6),
            "selection_margin_mm": selection_margin_mm,
            "export_body_start_x_mm": round(float(p.export_body_start_x), 6),
            "export_body_end_x_mm": round(float(p.export_body_end_x), 6),
            "export_bbox_min_x_mm": round(float(p.export_bbox_min_x), 6),
            "export_bbox_max_x_mm": round(float(p.export_bbox_max_x), 6),
            "grouped_flux_regions": ["prox", "mid", "dist"],
            "holes": holes,
            "axial_order": axial_order,
            "selection_helpers": {
                "strategy_a_preferred": "per_hole_local_spheres_or_cylinders_then_union_by_region",
                "strategy_b_mvp": "metadata_derived_region_boxes",
                "per_hole_local_selections": [
                    {
                        "hole_id": hole["hole_id"],
                        "region": hole["region"],
                        "type": hole["type"],
                        "center_mm": hole["center_mm"],
                        "normal": hole["normal"],
                        "sphere_radius_mm": hole["selection_sphere_radius_mm"],
                        "cylinder_radius_mm": hole["selection_cylinder_radius_mm"],
                    }
                    for hole in holes
                ],
                **selection_boxes,
            },
            "analysis_support": {
                "discrete_per_hole_flux_template": axial_order,
                "continuous_axial_profile_support": {
                    "axis_name": "axial_x_mm",
                    "x_min_mm": round(float(p.export_body_start_x), 6),
                    "x_max_mm": round(float(p.export_body_end_x), 6),
                    "hole_overlay_markers": axial_order,
                },
            },
            "validation": {
                "generator_consistency_tolerance_mm": validation_tolerance_mm,
                "validated_against_realized_generator_geometry": True,
            },
            # Backward-compatible aliases for existing helper code/docs.
            "region_selection_boxes": selection_boxes["region_selection_boxes"],
        }

    @staticmethod
    def _infer_design_id_from_sidecar_path(path: Path) -> str:
        stem = path.name
        if stem.endswith(".holes.json"):
            return stem[: -len(".holes.json")]
        return path.stem

    def export_hole_metadata(
        self,
        path: Path,
        design_id: Optional[str] = None,
        validation_tolerance_mm: float = 0.1,
    ) -> dict:
        """Write a JSON sidecar file with ground-truth hole coordinates for COMSOL.

        Conventionally placed next to the STEP file:
            stent.step  →  stent.holes.json

        The sidecar drives COMSOL Java selection building so that prox/mid/dist
        flux integrations never rely on hand-tuned bounding-box guesses.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = self.get_hole_metadata(
            design_id=design_id or self._infer_design_id_from_sidecar_path(path),
            validation_tolerance_mm=validation_tolerance_mm,
        )
        path.write_text(json.dumps(metadata, indent=2))
        return metadata

    def get_measurement_surface_metadata(
        self,
        design_id: Optional[str] = None,
        validation_tolerance_mm: float = 0.1,
        distal_annulus_outer_radius_mm: float = 4.0,
    ) -> dict:
        """Return metadata for automated COMSOL measurement surfaces."""
        if self._solid is None:
            raise RuntimeError(
                "Call generate() (or export_step / export_stl) before get_measurement_surface_metadata()."
            )

        p = self.params
        hole_entries = list(getattr(p, "export_hole_entries", []))
        self._validate_export_hole_entries(hole_entries, tolerance_mm=validation_tolerance_mm)

        sorted_entries = sorted(
            hole_entries,
            key=lambda entry: (
                round(float(entry["axial_x_mm"]), 9),
                0 if entry["type"] == "shaft" else 1,
                entry["hole_id"],
            ),
        )

        features: List[MeasurementFeature] = []
        hole_cap_ids_by_zone: Dict[str, List[str]] = {"prox": [], "mid": [], "dist": []}

        for entry in sorted_entries:
            center = entry["center_vec"]
            normal = entry["normal_vec"]

            if entry["type"] == "shaft":
                cap_center = center + (normal * p.r_inner)
                cap_normal = normal * -1.0
                feature_note = "shaft hole cap centered at the inner-wall opening"
            else:
                cap_center = center
                cap_normal = normal * -1.0
                feature_note = (
                    "coil hole cap currently uses the exported coil-hole center/axis; "
                    "dedicated coil-mouth reconstruction can refine this later"
                )

            feature = MeasurementFeature(
                feature_id=f"cap_hole_{entry['hole_id']}",
                feature_class="hole_cap",
                zone=entry["region"],
                geometry_type="cutplane_disk",
                center_mm=[round(value, 6) for value in self._vector_to_list(cap_center)],
                normal=[round(value, 9) for value in self._vector_to_list(cap_normal.normalized())],
                radius_mm=round(float(entry["radius_mm"]), 6),
                area_mm2=round(math.pi * float(entry["radius_mm"]) ** 2, 6),
                axial_x_mm=round(float(cap_center.X), 6),
                parent_feature=entry["hole_id"],
                source_type=entry["type"],
                metadata={
                    "source_hole_id": entry["hole_id"],
                    "source_hole_type": entry["type"],
                    "source_axial_x_mm": round(float(entry["axial_x_mm"]), 6),
                    "cap_center_rule": feature_note,
                },
            )
            features.append(feature)
            hole_cap_ids_by_zone[entry["region"]].append(feature.feature_id)

        distal_section_x_mm = self._compute_distal_partition_plane_x_mm()
        features.append(
            MeasurementFeature(
                feature_id="sec_distal_lumen",
                feature_class="cross_section",
                zone="dist",
                geometry_type="cutplane_disk",
                center_mm=[round(distal_section_x_mm, 6), 0.0, 0.0],
                normal=[1.0, 0.0, 0.0],
                radius_mm=round(float(p.r_inner), 6),
                area_mm2=round(math.pi * float(p.r_inner) ** 2, 6),
                axial_x_mm=round(distal_section_x_mm, 6),
                metadata={
                    "section_role": "distal_lumen_partition",
                    "placement_rule": "upstream_of_unroof_with_wall_clearance",
                    "safe_min_x_mm": round(float(p.distal_partition_min_x_body_mm), 6),
                    "safe_max_x_mm": round(float(p.distal_partition_max_x_body_mm), 6),
                },
            )
        )
        features.append(
            MeasurementFeature(
                feature_id="sec_distal_annulus",
                feature_class="cross_section",
                zone="dist",
                geometry_type="cutplane_annulus",
                center_mm=[round(distal_section_x_mm, 6), 0.0, 0.0],
                normal=[1.0, 0.0, 0.0],
                inner_radius_mm=round(float(p.r_outer), 6),
                outer_radius_mm=round(float(distal_annulus_outer_radius_mm), 6),
                area_mm2=round(
                    math.pi
                    * (
                        float(distal_annulus_outer_radius_mm) ** 2
                        - float(p.r_outer) ** 2
                    ),
                    6,
                ),
                axial_x_mm=round(distal_section_x_mm, 6),
                metadata={
                    "section_role": "distal_annulus_partition",
                    "placement_rule": "upstream_of_unroof_with_wall_clearance",
                    "safe_min_x_mm": round(float(p.distal_partition_min_x_body_mm), 6),
                    "safe_max_x_mm": round(float(p.distal_partition_max_x_body_mm), 6),
                },
            )
        )
        features.append(
            MeasurementFeature(
                feature_id="sec_inlet_ref",
                feature_class="pressure_ref",
                zone="prox",
                geometry_type="named_selection",
                selection_tag="inlet",
                metadata={"selection_role": "baseline_inlet_reference"},
            )
        )
        features.append(
            MeasurementFeature(
                feature_id="sec_outlet_ref",
                feature_class="pressure_ref",
                zone="dist",
                geometry_type="named_selection",
                selection_tag="outlet",
                metadata={"selection_role": "baseline_outlet_reference"},
            )
        )

        unroof_ids: List[str] = []
        if p.unroofed_length > 0:
            unroof_start_x = max(float(p.export_body_start_x), float(p.export_body_end_x) - float(p.unroofed_length))
            unroof_mid_x = (unroof_start_x + float(p.export_body_end_x)) / 2.0
            unroof_feature = MeasurementFeature(
                feature_id="patch_unroof_1",
                feature_class="unroof_patch",
                zone="dist",
                geometry_type="cutplane_rect",
                center_mm=[round(unroof_mid_x, 6), 0.0, 0.0],
                normal=[0.0, -1.0, 0.0],
                x_half_width_mm=round(float(p.unroofed_length) / 2.0, 6),
                z_half_width_mm=round(float(p.r_inner), 6),
                area_mm2=round(float(p.unroofed_length) * 2.0 * float(p.r_inner), 6),
                axial_x_mm=round(unroof_mid_x, 6),
                open_length_mm=round(float(p.unroofed_length), 6),
                metadata={"patch_role": "distal_unroof_exchange"},
            )
            features.append(unroof_feature)
            unroof_ids.append(unroof_feature.feature_id)

        inferred_design_id = design_id or getattr(p, "design_id", None) or "unknown_design"
        package = MeasurementSurfacePackage(
            design_id=inferred_design_id,
            schema_version="measurement_surface_sidecar_v1",
            units="mm",
            frame_definition={
                "name": "canonical_stent_export_frame",
                "body_axis": "+X",
                "body_axis_vector": [1.0, 0.0, 0.0],
                "body_start_at_x_mm": 0.0,
                "units": "mm",
            },
            features=features,
            grouped_flux_regions=["prox", "mid", "dist"],
            sign_convention={
                "exchange_flux": "positive_into_stent_lumen",
                "pressure_unit": "Pa",
                "flow_unit": "mL/min",
                "flux_density_unit": "mL/min/mm",
            },
            template_assumptions={
                "distal_annulus_outer_radius_mm": round(float(distal_annulus_outer_radius_mm), 6),
                "inlet_selection_tag": "inlet",
                "outlet_selection_tag": "outlet",
                "distal_partition_rule": "place the distal partition cross-sections inside the distal body and strictly upstream of the unroof by at least one outer-radius clearance",
                "notes": [
                    "Hole and unroof exchange surfaces are metadata-driven cut-plane patches.",
                    "Inlet/outlet references reuse stable named selections from the baseline COMSOL template.",
                ],
            },
            analysis_support={
                "hole_cap_ids_by_zone": hole_cap_ids_by_zone,
                "unroof_patch_ids": unroof_ids,
                "feature_ids": [feature.feature_id for feature in features],
                "distal_partition_window": {
                    "safe_min_x_mm": round(float(p.distal_partition_min_x_body_mm), 6),
                    "safe_max_x_mm": round(float(p.distal_partition_max_x_body_mm), 6),
                    "selected_x_mm": round(float(distal_section_x_mm), 6),
                },
            },
        )
        payload = package.to_dict()
        payload["feature_groups"] = {
            "hole_caps_all": [
                feature.feature_id for feature in features if feature.feature_class == "hole_cap"
            ],
            "hole_caps_by_zone": hole_cap_ids_by_zone,
            "cross_sections": [
                feature.feature_id for feature in features if feature.feature_class == "cross_section"
            ],
            "pressure_refs": [
                feature.feature_id for feature in features if feature.feature_class == "pressure_ref"
            ],
            "unroof_patches": unroof_ids,
        }
        payload["validation"] = {
            "generator_consistency_tolerance_mm": validation_tolerance_mm,
            "validated_against_export_hole_entries": True,
            "generator_warnings": list(getattr(p, "feasibility_warnings", [])),
        }
        return validate_measurement_surface_metadata(payload)

    def export_measurement_surface_metadata(
        self,
        path: Path,
        design_id: Optional[str] = None,
        validation_tolerance_mm: float = 0.1,
        distal_annulus_outer_radius_mm: float = 4.0,
    ) -> dict:
        """Write metadata that drives automated COMSOL extraction surfaces."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        inferred_design_id = design_id
        if inferred_design_id is None:
            if path.name.endswith(".meters.json"):
                inferred_design_id = path.name[: -len(".meters.json")]
            else:
                inferred_design_id = path.stem
        metadata = self.get_measurement_surface_metadata(
            design_id=inferred_design_id,
            validation_tolerance_mm=validation_tolerance_mm,
            distal_annulus_outer_radius_mm=distal_annulus_outer_radius_mm,
        )
        path.write_text(json.dumps(metadata, indent=2))
        return metadata

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
            "Requested n_prox/n_mid/n_dist": [
                p.requested_n_prox,
                p.requested_n_mid,
                p.requested_n_dist,
            ],
            "Realized n_prox/n_mid/n_dist": [
                p.realized_n_prox,
                p.realized_n_mid,
                p.realized_n_dist,
            ],
            "Realized Body Hole Area (mm^2)": round(
                getattr(p, "realized_body_hole_total_area", 0.0), 4
            ),
            "Realized Min Body Hole Spacing (mm)": (
                None
                if p.realized_body_hole_min_spacing is None
                else round(p.realized_body_hole_min_spacing, 4)
            ),
            "Realized Mean Body Hole Spacing (mm)": (
                None
                if p.realized_body_hole_mean_spacing is None
                else round(p.realized_body_hole_mean_spacing, 4)
            ),
            "Realized Nearest Neighbor Spacing (mm)": (
                None
                if p.realized_nearest_neighbor_spacing is None
                else round(p.realized_nearest_neighbor_spacing, 4)
            ),
            "Suppressed Holes (Unroofed)": p.suppressed_holes_due_to_unroofed,
            "Suppressed Holes (Clearance)": p.suppressed_holes_due_to_clearance,
            "Coil Holes Requested": coil_requested,
            "Coil Holes Realized": coil_realized,
            "Requested Midsection Hole Count": getattr(
                p, "requested_midsection_hole_count", p.requested_n_mid
            ),
            "Realized Midsection Hole Count": getattr(
                p, "realized_midsection_hole_count", p.realized_n_mid
            ),
            "Realized Total Hole Count": getattr(
                p, "realized_total_hole_count", p.realized_body_holes + coil_realized
            ),
            "Realized Total Hole Area (mm^2)": round(
                getattr(
                    p,
                    "realized_total_hole_area",
                    math.pi * (p.hole_radius**2) * (p.realized_body_holes + coil_realized),
                ),
                4,
            ),
            "Requested Hole Positions": [round(x, 1) for x in p.requested_hole_positions],
            "Realized Hole Positions": [round(x, 1) for x in p.realized_hole_positions],
            "Realized Arc Positions (deg)": [
                round(x, 1) for x in getattr(p, "realized_arc_positions", [])
            ],
            "Unroofed (mm)": p.unroofed_length,
            "Fixed Coil Geometry": p.freeze_coil_geometry,
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
        unroofed_length=10.0,
    )

    gen = StentGenerator(params)
    solid = gen.generate()

    out_path = Path("data/cad_exports/test_stent.step")
    gen.export_step(out_path)
    print(f"Exported to {out_path}")
    print(gen.get_info())
