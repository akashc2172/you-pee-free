"""Integration test: batch STL generation + QA pass rate.

Run with: RUN_STL_INTEGRATION=1 pytest src/cad/tests/test_stl_integration.py
"""

import os

import pytest

from src.cad.stent_generator import StentGenerator, StentParameters, StlExportOptions
from src.sampling.feasibility import FeasibilityFilter
from src.sampling.lhs_generator import LHSGenerator

pytest.importorskip("trimesh")


@pytest.mark.skipif(
    os.environ.get("RUN_STL_INTEGRATION") != "1",
    reason="Set RUN_STL_INTEGRATION=1 to run batch STL integration test.",
)
def test_stl_pass_rate_on_feasible_lhs_batch(tmp_path):
    """Feasible LHS designs should maintain very high STL QA pass rate."""
    lhs = LHSGenerator(seed=123)
    raw = lhs.generate(n_samples=120)
    feasible, _ = FeasibilityFilter().filter(raw)

    n = min(30, len(feasible))
    assert n == 30, "Need at least 30 feasible designs for integration pass-rate check"

    options = StlExportOptions.from_profile("standard", validate_mesh=True)

    passed = 0
    fail_reasons = []
    for i in range(n):
        params_dict = feasible.iloc[i].to_dict()
        params = StentParameters(**params_dict)
        gen = StentGenerator(params)
        out = tmp_path / f"design_{i:03d}.stl"
        try:
            meta = gen.export_stl(out, options=options)
            if meta["qa"] and meta["qa"]["passed"]:
                passed += 1
        except Exception as exc:
            fail_reasons.append(str(exc))

    pass_rate = passed / n
    assert pass_rate >= 0.99, f"STL QA pass rate {pass_rate:.3f} below 0.99; failures={fail_reasons}"
