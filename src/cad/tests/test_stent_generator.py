"""
Tests for the StentGenerator and StentParameters classes.
"""

import json
import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

from src.cad.mesh_quality import MeshQualityReport
from src.cad.stent_generator import StentGenerator, StentParameters, StlExportOptions


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TestStentParameters:
    """Tests for StentParameters validation and derivation."""
    
    def test_default_construction(self):
        """Default parameters should be valid."""
        params = StentParameters()
        assert params.OD > 0
        assert params.ID > 0
        assert params.ID < params.OD
    
    def test_id_min_constraint(self):
        """Should reject parameters that result in ID < ID_MIN."""
        with pytest.raises(ValueError, match="ID"):
            StentParameters(stent_french=4.0, r_t=0.30)  # Very thick wall
    
    def test_hole_packing_constraint(self):
        """Should reject if too many holes for section length."""
        with pytest.raises(ValueError, match="Cannot fit"):
            StentParameters(
                stent_length=100,
                section_length_prox=25,
                section_length_dist=25,
                n_mid=100,  # Way too many for 50mm middle
                r_sh=0.5
            )
    
    def test_middle_section_min(self):
        """Should reject if middle section < 10mm."""
        with pytest.raises(ValueError, match="Middle section"):
            StentParameters(
                stent_length=100,
                section_length_prox=50,
                section_length_dist=50  # Leaves 0mm for middle
            )
    
    def test_hole_positions_computed(self):
        """Hole positions should be computed correctly."""
        params = StentParameters(
            stent_length=150,
            section_length_prox=30,
            section_length_dist=30,
            n_prox=2,
            n_mid=3,
            n_dist=2
        )
        assert len(params.hole_positions) == 7
        assert all(0 < p < 150 for p in params.hole_positions)
        assert params.requested_body_holes == 7
        assert params.realized_body_holes == 7

    def test_unroofed_rebalances_distal_holes(self):
        """Unroofed distal region should suppress/rebalance overlapping distal holes."""
        params = StentParameters(
            stent_length=120,
            section_length_prox=45,
            section_length_dist=43,
            n_prox=8,
            n_mid=13,
            n_dist=10,
            unroofed_length=35,
            stent_french=4.7,
            r_t=0.2,
            r_sh=0.5,
        )
        assert params.requested_n_dist == 10
        assert params.realized_n_dist < params.requested_n_dist
        assert params.realized_body_holes < params.requested_body_holes
        assert (params.suppressed_holes_due_to_unroofed + params.suppressed_holes_due_to_clearance) > 0

    def test_unroofed_zero_keeps_requested(self):
        """No unroofing means requested and realized counts match."""
        params = StentParameters(unroofed_length=0, n_prox=3, n_mid=4, n_dist=2)
        assert params.realized_n_prox == params.requested_n_prox
        assert params.realized_n_mid == params.requested_n_mid
        assert params.realized_n_dist == params.requested_n_dist
    
    def test_derived_dimensions(self):
        """Check derived dimension calculations."""
        params = StentParameters(stent_french=6.0, r_t=0.15)
        expected_od = 0.333 * 6.0
        assert abs(params.OD - expected_od) < 0.001
        
        expected_wall = 0.15 * expected_od
        assert abs(params.wall_thickness - expected_wall) < 0.001
        
        expected_id = expected_od - 2 * expected_wall
        assert abs(params.ID - expected_id) < 0.001


class TestStentGenerator:
    """Tests for StentGenerator geometry creation."""
    
    def test_generate_basic(self):
        """Should generate a solid without errors."""
        params = StentParameters()
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None
    
    def test_generate_no_coils(self):
        """Should handle zero-turn coils."""
        params = StentParameters(turns_prox=0, turns_dist=0, freeze_coil_geometry=False)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None

    def test_coils_fixed_by_default(self):
        """Default behavior should pin coil geometry to fixed values."""
        params = StentParameters(coil_R_prox=9.0, pitch_prox=9.0, turns_prox=2.2)
        assert params.coil_R_prox == params.FIXED_COIL_R
        assert params.pitch_prox == params.FIXED_PITCH
        assert params.turns_prox == params.FIXED_TURNS
    
    def test_generate_with_unroofed(self):
        """Should handle unroofed section."""
        params = StentParameters(unroofed_length=15.0)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None
    
    def test_generate_minimal_holes(self):
        """Should handle zero holes."""
        params = StentParameters(n_prox=0, n_mid=0, n_dist=0)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None

    @pytest.mark.parametrize(
        "params",
        [
            StentParameters(),
            StentParameters(stent_length=220, n_mid=8, unroofed_length=12.0),
            StentParameters(turns_prox=0, turns_dist=0, freeze_coil_geometry=False),
        ],
    )
    def test_generate_normalizes_export_orientation(self, params):
        """Generated solids should export in a stable body-centered global frame."""
        gen = StentGenerator(params)
        solid = gen.generate()
        bbox = solid.bounding_box()
        tolerance = 1e-6

        assert solid is not None
        assert params.export_body_axis.X == pytest.approx(1.0, abs=tolerance)
        assert params.export_body_axis.Y == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_axis.Z == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_start_x == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_center_y == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_center_z == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_end.X > params.export_body_start.X
        assert params.export_body_end_x - params.export_body_start_x == pytest.approx(params.stent_length, abs=tolerance)
        assert bbox.min.X <= tolerance

    def test_generate_tracks_body_center_not_bbox_center(self):
        """Body-center metadata should refer to the straight shaft, not the whole-solid bbox center."""
        params = StentParameters()
        gen = StentGenerator(params)
        solid = gen.generate()
        bbox = solid.bounding_box()
        bbox_center_y = (bbox.min.Y + bbox.max.Y) / 2.0
        bbox_center_z = (bbox.min.Z + bbox.max.Z) / 2.0

        assert params.export_body_center_y == pytest.approx(0.0, abs=1e-6)
        assert params.export_body_center_z == pytest.approx(0.0, abs=1e-6)
        assert max(abs(bbox_center_y), abs(bbox_center_z)) > 1e-3

    def test_body_cross_sections_are_centered_on_actual_solid(self):
        """Actual straight-body cross-sections should be centered at y=z=0 after normalization."""
        params = StentParameters()
        gen = StentGenerator(params)
        solid = gen.generate()

        for center in gen._measure_body_cross_section_centers(solid):
            assert center.Y == pytest.approx(0.0, abs=1e-6)
            assert center.Z == pytest.approx(0.0, abs=1e-6)

    def test_body_center_metadata_matches_measured_cross_sections(self):
        """Helper metadata should come from measured shaft geometry, not only the body path."""
        params = StentParameters()
        gen = StentGenerator(params)
        solid = gen.generate()
        measured = gen._measure_body_cross_section_centers(solid)
        mean_y = sum(center.Y for center in measured) / len(measured)
        mean_z = sum(center.Z for center in measured) / len(measured)

        assert params.export_body_center_y == pytest.approx(mean_y, abs=1e-6)
        assert params.export_body_center_z == pytest.approx(mean_z, abs=1e-6)
        assert params.export_body_center_start.Y == pytest.approx(mean_y, abs=1e-6)
        assert params.export_body_center_start.Z == pytest.approx(mean_z, abs=1e-6)
        assert params.export_body_center_end.Y == pytest.approx(mean_y, abs=1e-6)
        assert params.export_body_center_end.Z == pytest.approx(mean_z, abs=1e-6)

    def test_export_step(self, tmp_path: Path):
        """Should export to STEP file."""
        params = StentParameters()
        gen = StentGenerator(params)
        
        out_path = tmp_path / "test_stent.step"
        gen.export_step(out_path)
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_export_step_uses_normalized_geometry(self, tmp_path: Path):
        """STEP export should use the canonicalized solid without extra COMSOL transforms."""
        params = StentParameters()
        gen = StentGenerator(params)
        out_path = tmp_path / "normalized.step"
        tolerance = 1e-6

        with patch("src.cad.stent_generator.export_step") as mock_export:
            gen.export_step(out_path)

        exported_solid = mock_export.call_args.args[0]
        bbox = exported_solid.bounding_box()

        assert params.export_body_axis.X == pytest.approx(1.0, abs=tolerance)
        assert params.export_body_axis.Y == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_axis.Z == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_start_x == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_center_y == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_center_z == pytest.approx(0.0, abs=tolerance)
        assert params.export_body_end.X > params.export_body_start.X
        assert bbox.min.X <= tolerance

    def test_print_comsol_template_values_helper(self, tmp_path: Path):
        """Helper script should emit deterministic template values from one design row."""
        campaign_dir = tmp_path / "campaign"
        campaign_dir.mkdir()
        pd_row = (
            "design_id,stent_french,stent_length,r_t,r_sh,r_end,n_prox,n_mid,n_dist,section_length_prox,section_length_dist,unroofed_length,cad_file\n"
            "design_0000,6.0,150,0.15,0.5,0.7,3,6,3,30,30,0," + str(campaign_dir / "cad" / "design_0000.step") + "\n"
        )
        (campaign_dir / "batch_0000.csv").write_text(pd_row)

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "print_comsol_template_values.py"),
            "--campaign_dir",
            str(campaign_dir),
            "--design_id",
            "design_0000",
            "--json",
        ]
        proc = subprocess.run(
            cmd,
            check=True,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        payload = json.loads(proc.stdout)
        values = payload["template_values"]

        assert payload["design_id"] == "design_0000"
        assert values["metadata"]["export_body_start_x"] == pytest.approx(0.0, abs=1e-6)
        assert values["metadata"]["export_body_center_y"] == pytest.approx(0.0, abs=1e-6)
        assert values["metadata"]["export_body_center_z"] == pytest.approx(0.0, abs=1e-6)
        assert values["cylinders"]["ureter"]["x"] == pytest.approx(0.0, abs=1e-6)
        assert values["cylinders"]["ureter"]["height_mm"] == pytest.approx(150.0, abs=1e-6)
        assert values["selection_boxes"]["coil_zone"]["proximal_x_range_mm"][1] == pytest.approx(0.0, abs=1e-6)
        assert values["selection_boxes"]["mid_zone"]["x_range_mm"] == pytest.approx([37.5, 112.5], abs=1e-6)
    
    def test_export_stl(self, tmp_path: Path):
        """Should export to STL file."""
        params = StentParameters()
        gen = StentGenerator(params)
        
        out_path = tmp_path / "test_stent.stl"
        info = gen.export_stl(out_path, options=StlExportOptions(validate_mesh=False))
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0
        assert info["path"] == str(out_path)
        assert info["qa"] is None

    def test_export_stl_profiles_apply_expected_tolerances(self, tmp_path: Path):
        """Profile defaults should map to expected tessellation tolerances."""
        params = StentParameters()
        gen = StentGenerator(params)
        out_path = tmp_path / "profile.stl"
        options = StlExportOptions.from_profile("high", validate_mesh=False)

        def _fake_export(_solid, file_path, **_kwargs):
            Path(file_path).write_text("solid mock\nendsolid mock\n")
            return True

        with patch("src.cad.stent_generator.export_stl", side_effect=_fake_export) as mock_export:
            gen.export_stl(out_path, options=options)

        _, kwargs = mock_export.call_args
        assert kwargs["tolerance"] == pytest.approx(0.0005)
        assert kwargs["angular_tolerance"] == pytest.approx(0.05)
        assert kwargs["ascii_format"] is False

    def test_export_stl_returns_metadata(self, tmp_path: Path):
        """STL export should include deterministic metadata and QA results."""
        params = StentParameters()
        gen = StentGenerator(params)
        out_path = tmp_path / "metadata.stl"

        report = MeshQualityReport(
            watertight=True,
            is_winding_consistent=True,
            is_volume=True,
            n_vertices=10,
            n_faces=20,
            euler_number=2,
            non_manifold_edges=0,
            degenerate_faces=0,
            self_intersection_suspected=False,
            passed=True,
            fail_reasons=[],
        )

        with patch("src.cad.stent_generator.validate_stl", return_value=report):
            info = gen.export_stl(out_path, options=StlExportOptions.from_profile("standard"))

        assert info["profile"] == "standard"
        assert info["qa"]["passed"] is True
        assert info["filesize_bytes"] > 0

    def test_export_stl_raises_on_failed_qa_when_validate_enabled(self, tmp_path: Path):
        """QA failure should raise with fail reasons when validation is enabled."""
        params = StentParameters()
        gen = StentGenerator(params)
        out_path = tmp_path / "badqa.stl"

        report = MeshQualityReport(
            watertight=False,
            is_winding_consistent=False,
            is_volume=False,
            n_vertices=10,
            n_faces=20,
            euler_number=1,
            non_manifold_edges=2,
            degenerate_faces=1,
            self_intersection_suspected=True,
            passed=False,
            fail_reasons=["not watertight", "non-manifold edges=2"],
        )

        with patch("src.cad.stent_generator.validate_stl", return_value=report):
            with pytest.raises(ValueError, match="STL QA failed"):
                gen.export_stl(out_path, options=StlExportOptions.from_profile("standard"))

    def test_export_stl_no_qa_when_disabled(self, tmp_path: Path):
        """QA function should not be called when validation is disabled."""
        params = StentParameters()
        gen = StentGenerator(params)
        out_path = tmp_path / "noqa.stl"
        options = StlExportOptions.from_profile("draft", validate_mesh=False)

        with patch("src.cad.stent_generator.validate_stl") as validate_mock:
            info = gen.export_stl(out_path, options=options)

        validate_mock.assert_not_called()
        assert info["qa"] is None
    
    def test_get_info(self):
        """Should return geometry summary."""
        params = StentParameters(stent_french=7.0, n_mid=5)
        gen = StentGenerator(params)
        gen.generate()
        
        info = gen.get_info()
        assert "French" in info
        assert info["French"] == 7.0
        assert "Total Holes" in info
        assert "Requested Body Holes" in info
        assert "Realized Body Holes" in info


class TestParameterRanges:
    """Test that parameter ranges from config are valid."""
    
    @pytest.mark.parametrize("french", [4.0, 5.0, 6.0, 7.0, 8.0])
    def test_french_range(self, french):
        """All French sizes in range should produce valid geometry."""
        params = StentParameters(stent_french=french)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None
    
    @pytest.mark.parametrize("r_t", [0.10, 0.15, 0.20])
    def test_wall_thickness_range(self, r_t):
        """Wall thickness fractions should produce valid geometry."""
        params = StentParameters(r_t=r_t)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None
