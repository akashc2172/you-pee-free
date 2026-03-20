"""Schema helpers for metadata-driven COMSOL measurement surfaces."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


VALID_FEATURE_CLASSES = {
    "hole_cap",
    "unroof_patch",
    "cross_section",
    "pressure_ref",
}

VALID_GEOMETRY_TYPES = {
    "cutplane_disk",
    "cutplane_annulus",
    "cutplane_rect",
    "named_selection",
}

VALID_ZONES = {"prox", "mid", "dist"}
VALID_SOURCE_TYPES = {"shaft", "coil"}
VALID_PRESSURE_SELECTION_ROLES = {
    "baseline_inlet_reference",
    "baseline_outlet_reference",
}
VALID_CROSS_SECTION_ROLES = {
    "distal_lumen_partition",
    "distal_annulus_partition",
}


@dataclass
class MeasurementFeature:
    feature_id: str
    feature_class: str
    zone: str
    geometry_type: str
    center_mm: Optional[List[float]] = None
    normal: Optional[List[float]] = None
    radius_mm: Optional[float] = None
    inner_radius_mm: Optional[float] = None
    outer_radius_mm: Optional[float] = None
    x_half_width_mm: Optional[float] = None
    z_half_width_mm: Optional[float] = None
    area_mm2: Optional[float] = None
    axial_x_mm: Optional[float] = None
    parent_feature: Optional[str] = None
    source_type: Optional[str] = None
    selection_tag: Optional[str] = None
    open_length_mm: Optional[float] = None
    sign_convention: str = "positive_into_stent_lumen"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class MeasurementSurfacePackage:
    design_id: str
    schema_version: str
    units: str
    frame_definition: Dict[str, Any]
    features: List[MeasurementFeature]
    grouped_flux_regions: List[str]
    sign_convention: Dict[str, str]
    template_assumptions: Dict[str, Any] = field(default_factory=dict)
    analysis_support: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design_id": self.design_id,
            "schema_version": self.schema_version,
            "units": self.units,
            "frame_definition": self.frame_definition,
            "grouped_flux_regions": self.grouped_flux_regions,
            "sign_convention": self.sign_convention,
            "template_assumptions": self.template_assumptions,
            "analysis_support": self.analysis_support,
            "features": [feature.to_dict() for feature in self.features],
        }


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _require_finite_vec3(values: Any, field_name: str, feature_id: str) -> List[float]:
    if not (isinstance(values, list) and len(values) == 3):
        raise ValueError(f"measurement_surface_invalid_{field_name}:{feature_id}")
    parsed = [float(value) for value in values]
    if not all(math.isfinite(value) for value in parsed):
        raise ValueError(f"measurement_surface_nonfinite_{field_name}:{feature_id}")
    return parsed


def _require_positive(value: Any, field_name: str, feature_id: str) -> float:
    if not _is_finite_number(value) or float(value) <= 0.0:
        raise ValueError(f"measurement_surface_invalid_{field_name}:{feature_id}")
    return float(value)


def _require_nonnegative(value: Any, field_name: str, feature_id: str) -> float:
    if not _is_finite_number(value) or float(value) < 0.0:
        raise ValueError(f"measurement_surface_invalid_{field_name}:{feature_id}")
    return float(value)


def _append_warning(warnings: List[str], code: str) -> None:
    if code not in warnings:
        warnings.append(code)


def validate_measurement_surface_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("measurement_surface_metadata_must_be_dict")
    if not isinstance(payload.get("features"), list):
        raise ValueError("measurement_surface_metadata_missing_features")
    if not isinstance(payload.get("frame_definition"), dict):
        raise ValueError("measurement_surface_metadata_missing_frame_definition")
    if payload.get("grouped_flux_regions") is not None:
        grouped_flux_regions = payload.get("grouped_flux_regions")
        if not isinstance(grouped_flux_regions, list) or not grouped_flux_regions:
            raise ValueError("measurement_surface_invalid_grouped_flux_regions")
        for zone in grouped_flux_regions:
            if str(zone).strip() not in VALID_ZONES:
                raise ValueError(f"measurement_surface_invalid_grouped_flux_region:{zone}")

    validation = dict(payload.get("validation") or {})
    warnings = list(validation.get("warnings") or [])

    seen_ids = set()
    hole_parent_ids = set()
    actual_by_zone: Dict[str, List[str]] = {zone: [] for zone in VALID_ZONES}
    actual_cross_sections: List[str] = []
    actual_pressure_refs: List[str] = []
    actual_unroof_patches: List[str] = []
    actual_hole_caps: List[str] = []
    unroof_intervals: List[tuple[float, float]] = []

    for feature in payload["features"]:
        if not isinstance(feature, dict):
            raise ValueError("measurement_surface_feature_not_dict")
        feature_id = str(feature.get("feature_id", "")).strip()
        if not feature_id:
            raise ValueError("measurement_surface_feature_missing_id")
        if feature_id in seen_ids:
            raise ValueError(f"duplicate_measurement_surface_feature_id:{feature_id}")
        seen_ids.add(feature_id)

        feature_class = str(feature.get("feature_class", "")).strip()
        if feature_class not in VALID_FEATURE_CLASSES:
            raise ValueError(f"invalid_measurement_surface_feature_class:{feature_id}")

        zone = str(feature.get("zone", "")).strip()
        if zone not in VALID_ZONES:
            raise ValueError(f"invalid_measurement_surface_zone:{feature_id}")
        actual_by_zone[zone].append(feature_id)

        geometry_type = str(feature.get("geometry_type", "")).strip()
        if geometry_type not in VALID_GEOMETRY_TYPES:
            raise ValueError(f"invalid_measurement_surface_geometry_type:{feature_id}")

        sign_convention = str(feature.get("sign_convention", "")).strip()
        if sign_convention and sign_convention != "positive_into_stent_lumen":
            raise ValueError(f"measurement_surface_invalid_sign_convention:{feature_id}")

        if geometry_type == "named_selection":
            if not str(feature.get("selection_tag", "")).strip():
                raise ValueError(f"measurement_surface_missing_selection_tag:{feature_id}")
            if feature_class != "pressure_ref":
                raise ValueError(f"measurement_surface_named_selection_wrong_class:{feature_id}")
            actual_pressure_refs.append(feature_id)
            selection_role = str((feature.get("metadata") or {}).get("selection_role", "")).strip()
            if selection_role not in VALID_PRESSURE_SELECTION_ROLES:
                raise ValueError(f"measurement_surface_invalid_pressure_ref_role:{feature_id}")
            selection_tag = str(feature.get("selection_tag", "")).strip()
            if selection_role == "baseline_inlet_reference" and selection_tag != "inlet":
                raise ValueError(f"measurement_surface_pressure_ref_must_use_inlet:{feature_id}")
            if selection_role == "baseline_outlet_reference" and selection_tag != "outlet":
                raise ValueError(f"measurement_surface_pressure_ref_must_use_outlet:{feature_id}")
        else:
            center = _require_finite_vec3(feature.get("center_mm"), "center", feature_id)
            normal = _require_finite_vec3(feature.get("normal"), "normal", feature_id)
            normal_norm = math.sqrt(sum(value * value for value in normal))
            if normal_norm < 1e-9:
                raise ValueError(f"measurement_surface_zero_normal:{feature_id}")
            if abs(normal_norm - 1.0) > 1e-3:
                raise ValueError(f"measurement_surface_nonunit_normal:{feature_id}")

            if not _is_finite_number(feature.get("axial_x_mm")):
                raise ValueError(f"measurement_surface_invalid_axial_x:{feature_id}")
            area_mm2 = _require_positive(feature.get("area_mm2"), "area_mm2", feature_id)

            if geometry_type == "cutplane_disk":
                radius_mm = _require_positive(feature.get("radius_mm"), "radius_mm", feature_id)
                expected_area = math.pi * radius_mm * radius_mm
                if abs(area_mm2 - expected_area) > max(1e-6, 1e-3 * expected_area):
                    raise ValueError(f"measurement_surface_area_mismatch:{feature_id}")
            elif geometry_type == "cutplane_annulus":
                inner_radius_mm = _require_positive(
                    feature.get("inner_radius_mm"), "inner_radius_mm", feature_id
                )
                outer_radius_mm = _require_positive(
                    feature.get("outer_radius_mm"), "outer_radius_mm", feature_id
                )
                if outer_radius_mm <= inner_radius_mm:
                    raise ValueError(f"measurement_surface_invalid_annulus_radii:{feature_id}")
                expected_area = math.pi * (
                    outer_radius_mm * outer_radius_mm - inner_radius_mm * inner_radius_mm
                )
                if abs(area_mm2 - expected_area) > max(1e-6, 1e-3 * expected_area):
                    raise ValueError(f"measurement_surface_area_mismatch:{feature_id}")
            elif geometry_type == "cutplane_rect":
                x_half_width_mm = _require_positive(
                    feature.get("x_half_width_mm"), "x_half_width_mm", feature_id
                )
                z_half_width_mm = _require_positive(
                    feature.get("z_half_width_mm"), "z_half_width_mm", feature_id
                )
                expected_area = 4.0 * x_half_width_mm * z_half_width_mm
                if abs(area_mm2 - expected_area) > max(1e-6, 1e-3 * expected_area):
                    raise ValueError(f"measurement_surface_area_mismatch:{feature_id}")

            if feature_class == "hole_cap":
                actual_hole_caps.append(feature_id)
                hole_match = re.fullmatch(
                    r"cap_hole_(shaft|coil)_(prox|mid|dist)_(\d{3})",
                    feature_id,
                )
                if hole_match is None:
                    raise ValueError(f"measurement_surface_invalid_hole_cap_id:{feature_id}")
                source_type = str(feature.get("source_type", "")).strip()
                if source_type not in VALID_SOURCE_TYPES:
                    raise ValueError(f"measurement_surface_invalid_source_type:{feature_id}")
                if hole_match.group(1) != source_type:
                    raise ValueError(f"measurement_surface_hole_cap_source_type_mismatch:{feature_id}")
                if hole_match.group(2) != zone:
                    raise ValueError(f"measurement_surface_hole_cap_zone_mismatch:{feature_id}")
                parent_feature = str(feature.get("parent_feature", "")).strip()
                if not parent_feature:
                    raise ValueError(f"measurement_surface_missing_parent_feature:{feature_id}")
                if parent_feature in hole_parent_ids:
                    raise ValueError(f"measurement_surface_duplicate_parent_feature:{parent_feature}")
                hole_parent_ids.add(parent_feature)
                metadata = feature.get("metadata") or {}
                source_hole_id = str(metadata.get("source_hole_id", "")).strip()
                if source_hole_id and source_hole_id != parent_feature:
                    raise ValueError(f"measurement_surface_parent_feature_traceability_mismatch:{feature_id}")

            elif feature_class == "unroof_patch":
                actual_unroof_patches.append(feature_id)
                if re.fullmatch(r"patch_unroof_\d+", feature_id) is None:
                    raise ValueError(f"measurement_surface_invalid_unroof_patch_id:{feature_id}")
                if zone != "dist":
                    raise ValueError(f"measurement_surface_unroof_patch_must_be_dist:{feature_id}")
                open_length_mm = _require_positive(
                    feature.get("open_length_mm"), "open_length_mm", feature_id
                )
                x_half_width_mm = float(feature.get("x_half_width_mm"))
                if abs((2.0 * x_half_width_mm) - open_length_mm) > max(1e-6, 1e-3 * open_length_mm):
                    raise ValueError(f"measurement_surface_unroof_open_length_mismatch:{feature_id}")
                center_x = float(center[0])
                unroof_intervals.append((center_x - (open_length_mm / 2.0), center_x + (open_length_mm / 2.0)))

            elif feature_class == "cross_section":
                actual_cross_sections.append(feature_id)
                if feature_id not in {"sec_distal_lumen", "sec_distal_annulus"}:
                    raise ValueError(f"measurement_surface_invalid_cross_section_id:{feature_id}")
                section_role = str((feature.get("metadata") or {}).get("section_role", "")).strip()
                if section_role not in VALID_CROSS_SECTION_ROLES:
                    raise ValueError(f"measurement_surface_invalid_cross_section_role:{feature_id}")
                if feature_id == "sec_distal_lumen":
                    if geometry_type != "cutplane_disk" or section_role != "distal_lumen_partition":
                        raise ValueError(f"measurement_surface_cross_section_contract_mismatch:{feature_id}")
                if feature_id == "sec_distal_annulus":
                    if geometry_type != "cutplane_annulus" or section_role != "distal_annulus_partition":
                        raise ValueError(f"measurement_surface_cross_section_contract_mismatch:{feature_id}")

            elif feature_class == "pressure_ref":
                raise ValueError(f"measurement_surface_pressure_ref_requires_named_selection:{feature_id}")

    for feature in payload["features"]:
        feature_class = str(feature.get("feature_class", "")).strip()
        if feature_class != "cross_section":
            continue
        feature_id = str(feature.get("feature_id", "")).strip()
        axial_x = float(feature.get("axial_x_mm"))
        for unroof_start_x, unroof_end_x in unroof_intervals:
            if (unroof_start_x - 1e-6) <= axial_x <= (unroof_end_x + 1e-6):
                raise ValueError(f"measurement_surface_distal_partition_inside_unroof:{feature_id}")

    feature_groups = payload.get("feature_groups")
    if feature_groups is not None:
        if not isinstance(feature_groups, dict):
            raise ValueError("measurement_surface_invalid_feature_groups")
        listed_all = set(feature_groups.get("hole_caps_all", []))
        if listed_all and listed_all != set(actual_hole_caps):
            raise ValueError("measurement_surface_feature_groups_hole_caps_all_mismatch")
        listed_cross_sections = set(feature_groups.get("cross_sections", []))
        if listed_cross_sections and listed_cross_sections != set(actual_cross_sections):
            raise ValueError("measurement_surface_feature_groups_cross_sections_mismatch")
        listed_pressure_refs = set(feature_groups.get("pressure_refs", []))
        if listed_pressure_refs and listed_pressure_refs != set(actual_pressure_refs):
            raise ValueError("measurement_surface_feature_groups_pressure_refs_mismatch")
        listed_unroof = set(feature_groups.get("unroof_patches", []))
        if listed_unroof and listed_unroof != set(actual_unroof_patches):
            raise ValueError("measurement_surface_feature_groups_unroof_patches_mismatch")
        listed_by_zone = feature_groups.get("hole_caps_by_zone")
        if listed_by_zone is not None:
            if not isinstance(listed_by_zone, dict):
                raise ValueError("measurement_surface_invalid_hole_caps_by_zone")
            for zone in VALID_ZONES:
                if set(listed_by_zone.get(zone, [])) != set(actual_by_zone[zone]).intersection(actual_hole_caps):
                    raise ValueError(f"measurement_surface_feature_groups_hole_caps_by_zone_mismatch:{zone}")

    analysis_support = payload.get("analysis_support")
    if analysis_support is not None:
        if not isinstance(analysis_support, dict):
            raise ValueError("measurement_surface_invalid_analysis_support")
        feature_ids = analysis_support.get("feature_ids")
        if feature_ids is not None and set(feature_ids) != seen_ids:
            raise ValueError("measurement_surface_analysis_support_feature_ids_mismatch")
        hole_cap_ids_by_zone = analysis_support.get("hole_cap_ids_by_zone")
        if hole_cap_ids_by_zone is not None:
            for zone in VALID_ZONES:
                if set(hole_cap_ids_by_zone.get(zone, [])) != set(actual_by_zone[zone]).intersection(actual_hole_caps):
                    raise ValueError(f"measurement_surface_analysis_support_hole_caps_by_zone_mismatch:{zone}")
        unroof_patch_ids = analysis_support.get("unroof_patch_ids")
        if unroof_patch_ids is not None and set(unroof_patch_ids) != set(actual_unroof_patches):
            raise ValueError("measurement_surface_analysis_support_unroof_patch_ids_mismatch")

    grouped_flux_regions = payload.get("grouped_flux_regions") or []
    if grouped_flux_regions and list(grouped_flux_regions) != ["prox", "mid", "dist"]:
        _append_warning(warnings, "nonstandard_grouped_flux_region_order")

    validation["warnings"] = warnings
    payload["validation"] = validation

    return payload
