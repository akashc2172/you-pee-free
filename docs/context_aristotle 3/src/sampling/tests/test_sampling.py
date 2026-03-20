"""
Tests for LHS Generator and Feasibility Filter.
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from src.sampling.lhs_generator import LHSGenerator
from src.sampling.feasibility import FeasibilityFilter
from src.utils.config import ConfigLoader

class TestConfigLoader:
    def test_load_defaults(self):
        loader = ConfigLoader()
        assert 'stent_french' in loader.design_vars
        assert loader.design_vars['stent_french'].default == 6.0
        assert loader.get_sim_contract_version() == "v1_deltaP490_steady_laminar"
        assert loader.get_simulation_contract().get("domain_template") == "triple_domain_dumbbell"
        
    def test_get_bounds(self):
        loader = ConfigLoader()
        bounds = loader.get_bounds_list()
        assert len(bounds) == len(loader.design_vars)
        assert bounds[0] is not None

class TestLHSGenerator:
    def test_generator_structure(self):
        gen = LHSGenerator(seed=42)
        df = gen.generate(n_samples=10)
        
        assert len(df) == 10
        # Check columns
        config = ConfigLoader()
        expected_cols = set(config.get_parameter_names())
        assert set(df.columns) == expected_cols
        
    def test_bounds_respected(self):
        gen = LHSGenerator(seed=42)
        df = gen.generate(n_samples=50)
        config = ConfigLoader()
        
        for var, conf in config.design_vars.items():
            min_val, max_val = conf.range
            assert df[var].min() >= min_val
            assert df[var].max() <= max_val
            
    def test_discrete_vars(self):
        gen = LHSGenerator(seed=42)
        df = gen.generate(n_samples=10)
        
        # n_mid is discrete
        assert pd.api.types.is_integer_dtype(df['n_mid'])
        # check it contains integers
        assert (df['n_mid'] % 1 == 0).all()

    def test_fixed_param_removes_dimension_and_stamps_output(self):
        gen = LHSGenerator(seed=42, fixed_params={"stent_length": 140.0})
        df = gen.generate(n_samples=8)

        assert "stent_length" in df.columns
        assert (df["stent_length"] == 140.0).all()
        assert "stent_length" not in gen.param_names
        assert gen.n_dims == len(ConfigLoader().get_parameter_names()) - 1

class TestFeasibilityFilter:
    def test_valid_design(self):
        # Manually create a known valid row
        valid_row = {
            'stent_french': 6.0,
            'stent_length': 150.0,
            'r_t': 0.15,
            'r_sh': 0.5,
            'r_end': 0.7,
            'section_length_prox': 30.0,
            'section_length_dist': 30.0,
            'n_prox': 2,
            'n_mid': 5,
            'n_dist': 2,
            # include other required fields with defaults if needed
            'coil_R_prox': 6.0, 'pitch_prox': 6.0, 'turns_prox': 1.5,
            'coil_R_dist': 6.0, 'pitch_dist': 6.0, 'turns_dist': 1.5,
            'unroofed_length': 0.0
        }
        df = pd.DataFrame([valid_row])
        filt = FeasibilityFilter()
        valid_df, report = filt.filter(df)
        
        assert len(valid_df) == 1
        assert report.n_valid == 1
        assert not report.rejection_reasons

    def test_invalid_id_min(self):
        # French 4.0 (OD=1.33) with r_t=0.22 (Wall=0.29) -> ID = 1.33 - 0.58 = 0.75 (>0.6)
        # Wait, let's try to break ID_min=0.6
        # French 4.0 (OD=1.332). Wall=r_t*OD. ID = OD*(1-2r_t).
        # if r_t=0.3 -> ID = 1.33*0.4 = 0.53 (<0.6).
        # But r_t range is [0.10, 0.22]. Max r_t=0.22.
        # Min OD = 4.0 * 0.333 = 1.332.
        # Min ID = 1.332 * (1 - 2*0.22) = 1.332 * 0.56 = 0.74.
        # So actually ID_min is practically impossible to violate with current ranges!
        # Good design by me.
        # Let's force a bad value manually to test the filter logic.
        
        bad_row = {
            'stent_french': 2.0, # Illegal, but filter checks row
            'r_t': 0.15,
            # needs other cols
             'stent_length': 150.0, 'r_sh': 0.5, 'r_end': 0.7,
            'section_length_prox': 30.0, 'section_length_dist': 30.0,
            'n_prox': 2, 'n_mid': 5, 'n_dist': 2,
             'coil_R_prox': 6.0, 'pitch_prox': 6.0, 'turns_prox': 1.5,
            'coil_R_dist': 6.0, 'pitch_dist': 6.0, 'turns_dist': 1.5,
            'unroofed_length': 0.0
        }
        df = pd.DataFrame([bad_row])
        filt = FeasibilityFilter()
        valid_df, report = filt.filter(df)
        
        assert len(valid_df) == 0
        assert "ID < ID_MIN" in report.rejection_reasons
        
    def test_packing_failure(self):
        # try to pack too many holes
        bad_row = {
            'stent_french': 6.0,
            'stent_length': 150.0,
            'section_length_prox': 20.0,
            'n_prox': 100, # Impossible
            'r_t': 0.15, 'r_sh': 0.5, 'r_end': 0.7,
            'section_length_dist': 30.0, 'n_mid': 0, 'n_dist': 0,
             'coil_R_prox': 6.0, 'pitch_prox': 6.0, 'turns_prox': 1.5,
            'coil_R_dist': 6.0, 'pitch_dist': 6.0, 'turns_dist': 1.5,
            'unroofed_length': 0.0
        }
        df = pd.DataFrame([bad_row])
        filt = FeasibilityFilter()
        valid_df, report = filt.filter(df)
        
        assert len(valid_df) == 0
        assert "Hole packing (prox)" in report.rejection_reasons

    def test_unroof_overlap_is_warning_not_rejection(self):
        row = {
            'stent_french': 4.7,
            'stent_length': 120.0,
            'r_t': 0.2,
            'r_sh': 0.5,
            'r_end': 0.3,
            'section_length_prox': 45.0,
            'section_length_dist': 43.0,
            'n_prox': 8,
            'n_mid': 13,
            'n_dist': 10,
            'coil_R_prox': 6.0, 'pitch_prox': 6.0, 'turns_prox': 1.5,
            'coil_R_dist': 4.0, 'pitch_dist': 10.0, 'turns_dist': 0.5,
            'unroofed_length': 35.0,
        }
        df = pd.DataFrame([row])
        filt = FeasibilityFilter()
        valid_df, report = filt.filter(df)
        assert len(valid_df) == 1
        assert report.rejection_reasons == {}
        assert report.warning_reasons.get("requires_rebalance", 0) == 1

    def test_distal_partition_infeasible_is_rejected(self):
        row = {
            'stent_french': 6.0,
            'stent_length': 100.0,
            'r_t': 0.15,
            'r_sh': 0.5,
            'r_end': 0.7,
            'section_length_prox': 20.0,
            'section_length_dist': 20.0,
            'n_prox': 2,
            'n_mid': 3,
            'n_dist': 2,
            'coil_R_prox': 6.0, 'pitch_prox': 6.0, 'turns_prox': 1.5,
            'coil_R_dist': 6.0, 'pitch_dist': 6.0, 'turns_dist': 1.5,
            'unroofed_length': 20.0,
        }
        df = pd.DataFrame([row])
        filt = FeasibilityFilter()
        valid_df, report = filt.filter(df)

        assert len(valid_df) == 0
        assert report.rejection_reasons.get("Distal partition infeasible", 0) == 1
