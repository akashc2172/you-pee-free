from __future__ import annotations

import pytest

from src.cad.stent_generator import StentGenerator, StentParameters
from src.measurement_surfaces.schema import validate_measurement_surface_metadata


def test_generated_measurement_metadata_places_distal_partition_upstream_of_unroof():
    params = StentParameters(
        stent_french=6.0,
        stent_length=140.0,
        section_length_prox=30.0,
        section_length_dist=30.0,
        n_prox=2,
        n_mid=5,
        n_dist=2,
        unroofed_length=10.0,
    )
    generator = StentGenerator(params)
    generator.generate()
    metadata = generator.get_measurement_surface_metadata(design_id="design_0000")

    by_id = {feature["feature_id"]: feature for feature in metadata["features"]}
    unroof = by_id["patch_unroof_1"]
    distal_lumen = by_id["sec_distal_lumen"]

    unroof_start_x = float(unroof["axial_x_mm"]) - (float(unroof["open_length_mm"]) / 2.0)
    assert float(distal_lumen["axial_x_mm"]) < unroof_start_x
    assert metadata["analysis_support"]["distal_partition_window"]["selected_x_mm"] == pytest.approx(
        distal_lumen["axial_x_mm"]
    )


def test_validation_rejects_distal_partition_inside_unroof():
    payload = {
        "design_id": "design_bad",
        "schema_version": "measurement_surface_sidecar_v1",
        "units": "mm",
        "frame_definition": {"name": "canonical", "units": "mm"},
        "grouped_flux_regions": ["prox", "mid", "dist"],
        "sign_convention": {"exchange_flux": "positive_into_stent_lumen"},
        "features": [
            {
                "feature_id": "sec_distal_lumen",
                "feature_class": "cross_section",
                "zone": "dist",
                "geometry_type": "cutplane_disk",
                "center_mm": [95.0, 0.0, 0.0],
                "normal": [1.0, 0.0, 0.0],
                "radius_mm": 0.5,
                "area_mm2": 0.7853981634,
                "axial_x_mm": 95.0,
                "sign_convention": "positive_into_stent_lumen",
                "metadata": {"section_role": "distal_lumen_partition"},
            },
            {
                "feature_id": "sec_distal_annulus",
                "feature_class": "cross_section",
                "zone": "dist",
                "geometry_type": "cutplane_annulus",
                "center_mm": [95.0, 0.0, 0.0],
                "normal": [1.0, 0.0, 0.0],
                "inner_radius_mm": 0.75,
                "outer_radius_mm": 4.0,
                "area_mm2": 48.498006245,
                "axial_x_mm": 95.0,
                "sign_convention": "positive_into_stent_lumen",
                "metadata": {"section_role": "distal_annulus_partition"},
            },
            {
                "feature_id": "patch_unroof_1",
                "feature_class": "unroof_patch",
                "zone": "dist",
                "geometry_type": "cutplane_rect",
                "center_mm": [95.0, 0.0, 0.0],
                "normal": [0.0, -1.0, 0.0],
                "x_half_width_mm": 5.0,
                "z_half_width_mm": 0.5,
                "area_mm2": 10.0,
                "axial_x_mm": 95.0,
                "open_length_mm": 10.0,
                "sign_convention": "positive_into_stent_lumen",
                "metadata": {"patch_role": "distal_unroof_exchange"},
            },
            {
                "feature_id": "sec_inlet_ref",
                "feature_class": "pressure_ref",
                "zone": "prox",
                "geometry_type": "named_selection",
                "selection_tag": "inlet",
                "metadata": {"selection_role": "baseline_inlet_reference"},
            },
            {
                "feature_id": "sec_outlet_ref",
                "feature_class": "pressure_ref",
                "zone": "dist",
                "geometry_type": "named_selection",
                "selection_tag": "outlet",
                "metadata": {"selection_role": "baseline_outlet_reference"},
            },
        ],
    }

    with pytest.raises(ValueError, match="measurement_surface_distal_partition_inside_unroof"):
        validate_measurement_surface_metadata(payload)
