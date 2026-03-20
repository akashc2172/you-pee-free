from pathlib import Path

import trimesh

from src.visualization.hole_metadata_viewer import (
    export_hole_metadata_viewer,
    write_viewer_html,
)


def _fake_metadata() -> dict:
    return {
        "design_id": "design_0000",
        "r_outer_mm": 1.0,
        "export_body_start_x_mm": 0.0,
        "export_body_end_x_mm": 10.0,
        "holes": [
            {
                "hole_id": "shaft_mid_000",
                "region": "mid",
                "type": "shaft",
                "center_mm": [5.0, 0.0, 0.0],
                "normal": [0.0, 1.0, 0.0],
            },
            {
                "hole_id": "coil_dist_000",
                "region": "dist",
                "type": "coil",
                "center_mm": [9.0, 2.0, 1.0],
                "normal": [1.0, 0.0, 0.0],
            },
        ],
    }


def _fake_measurement_metadata() -> dict:
    return {
        "features": [
            {
                "feature_id": "cap_hole_shaft_mid_000",
                "feature_class": "hole_cap",
                "zone": "mid",
                "geometry_type": "cutplane_disk",
                "center_mm": [5.0, 0.8, 0.0],
                "normal": [0.0, -1.0, 0.0],
                "radius_mm": 0.5,
            },
            {
                "feature_id": "sec_distal_lumen",
                "feature_class": "cross_section",
                "zone": "dist",
                "geometry_type": "cutplane_disk",
                "center_mm": [9.0, 0.0, 0.0],
                "normal": [1.0, 0.0, 0.0],
                "radius_mm": 0.8,
            },
            {
                "feature_id": "patch_unroof_1",
                "feature_class": "unroof_patch",
                "zone": "dist",
                "geometry_type": "cutplane_rect",
                "center_mm": [8.0, 0.0, 0.0],
                "normal": [0.0, -1.0, 0.0],
                "x_half_width_mm": 1.5,
                "z_half_width_mm": 0.5,
            },
            {
                "feature_id": "sec_inlet_ref",
                "feature_class": "pressure_ref",
                "zone": "prox",
                "geometry_type": "named_selection",
                "selection_tag": "inlet",
            },
        ]
    }


def test_write_viewer_html_includes_measurement_sections(tmp_path: Path):
    html_path = tmp_path / "viewer.html"
    mesh = trimesh.creation.box(extents=[10.0, 2.0, 2.0])
    write_viewer_html(
        html_path=html_path,
        step_filename="viewer.step",
        holes_filename="viewer.holes.json",
        meters_filename="viewer.meters.json",
        metadata=_fake_metadata(),
        measurement_metadata=_fake_measurement_metadata(),
        mesh=mesh,
        show_shaft=True,
        show_coil=True,
    )

    html = html_path.read_text()
    assert "design_0000" in html
    assert "<canvas" in html
    assert "three.min.js" in html
    assert "OrbitControls.legacy.js" in html
    assert "Hole caps" in html
    assert "Cross-sections" in html
    assert "Unroof patch" in html
    assert "viewer.meters.json" in html
    # No <model-viewer auto-rotate>; text may mention auto-rotate.
    assert "<model-viewer" not in html
    assert "Stent</span>" in html
    assert "Shaft hole point + normal" in html
    assert "Coil hole point + normal" in html
    assert "Drag to rotate. Wheel to zoom. Right-drag to pan." in html
    assert "var VIEWER_DATA =" in html


def test_export_hole_metadata_viewer_autodetects_meters_json(tmp_path: Path):
    step_path = tmp_path / "design_0000.step"
    holes_path = tmp_path / "design_0000.holes.json"
    meters_path = tmp_path / "design_0000.meters.json"

    step_path.write_text("dummy")
    holes_path.write_text(
        '{"design_id":"design_0000","r_outer_mm":1.0,"export_body_start_x_mm":0.0,"export_body_end_x_mm":10.0,"holes":[]}'
    )
    meters_path.write_text('{"features":[]}')

    from unittest.mock import patch

    with patch("src.visualization.hole_metadata_viewer.load_step_as_trimesh", return_value=trimesh.creation.box(extents=[10.0, 2.0, 2.0])):
        outputs = export_hole_metadata_viewer(
            step_path=step_path,
            holes_json=holes_path,
            output_dir=tmp_path / "viewer",
        )

    assert Path(outputs["html"]).exists()
    assert Path(outputs["glb"]).exists()
    assert outputs["meters_json"].endswith("design_0000.meters.json")
    assert (tmp_path / "viewer" / "vendor" / "three.min.js").exists()
    assert (tmp_path / "viewer" / "vendor" / "OrbitControls.legacy.js").exists()
