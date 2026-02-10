"""
Tests for the StentGenerator and StentParameters classes.
"""

import pytest
from pathlib import Path

from src.cad.stent_generator import StentGenerator, StentParameters


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
        params = StentParameters(turns_prox=0, turns_dist=0)
        gen = StentGenerator(params)
        solid = gen.generate()
        assert solid is not None
    
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
    
    def test_export_step(self, tmp_path: Path):
        """Should export to STEP file."""
        params = StentParameters()
        gen = StentGenerator(params)
        
        out_path = tmp_path / "test_stent.step"
        gen.export_step(out_path)
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_export_stl(self, tmp_path: Path):
        """Should export to STL file."""
        params = StentParameters()
        gen = StentGenerator(params)
        
        out_path = tmp_path / "test_stent.stl"
        gen.export_stl(out_path)
        
        assert out_path.exists()
        assert out_path.stat().st_size > 0
    
    def test_get_info(self):
        """Should return geometry summary."""
        params = StentParameters(stent_french=7.0, n_mid=5)
        gen = StentGenerator(params)
        gen.generate()
        
        info = gen.get_info()
        assert "French" in info
        assert info["French"] == 7.0
        assert "Total Holes" in info


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
