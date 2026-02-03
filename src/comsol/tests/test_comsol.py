"""
Tests for COMSOL Automation Module.
"""

import pytest
from pathlib import Path
import pandas as pd
from unittest.mock import patch, MagicMock

from src.comsol.result_parser import ResultParser, COMSOLResult
from src.comsol.runner import COMSOLRunner

class TestResultParser:
    
    @pytest.fixture
    def mock_run_dir(self, tmp_path):
        """Create a mock run directory with log and results."""
        run_id = "design_001"
        d = tmp_path / run_id
        d.mkdir()
        
        # Create CSV
        csv_content = """
% Model: test.mph
% Version: COMSOL 6.0
Q_out, delta_P, Q_sh1, Q_mid, Q_end
100.5, 5000.2, 10.1, 20.2, 15.5
        """.strip()
        (d / f"{run_id}_results.csv").write_text(csv_content)
        
        # Create Log
        log_content = """
...
Solving...
Iter 1: error 1.0
Iter 42: error 1e-4
Solution time: 123.45 s
Solver finished.
        """.strip()
        (d / f"{run_id}.log").write_text(log_content)
        
        return d, run_id

    def test_parse_success(self, mock_run_dir):
        run_dir, run_id = mock_run_dir
        parser = ResultParser()
        result = parser.parse_run(run_dir, run_id)
        
        # Check metrics
        assert result.q_out == 100.5
        assert result.delta_p == 5000.2
        assert result.q_sh['q_sh1'] == 10.1
        
        # Check diagnostics
        assert result.converged is True
        assert result.cpu_time_s == 123.45
        assert not result.errors

    def test_parse_failure(self, tmp_path):
        """Test parsing a non-existent run."""
        parser = ResultParser()
        result = parser.parse_run(tmp_path / "fake", "fake_id")
        
        assert not result.converged
        assert len(result.errors) > 0
        assert any("not found" in e for e in result.errors)
        
    def test_convergence_failure(self, tmp_path):
        """Test log with error."""
        run_id = "fail_run"
        d = tmp_path / run_id
        d.mkdir()
        (d / f"{run_id}_results.csv").touch() # Empty
        (d / f"{run_id}.log").write_text("Error: Divergence detected.")
        
        parser = ResultParser()
        result = parser.parse_run(d, run_id)
        
        assert result.converged is False
        assert "Error: Divergence detected." in result.errors


class TestCOMSOLRunner:
    @patch('subprocess.run')
    def test_run_batch(self, mock_sub, tmp_path):
        """Test command construction."""
        runner = COMSOLRunner(
            comsol_exec="/usr/local/bin/comsol",
            base_mph=tmp_path / "base.mph",
            output_dir=tmp_path / "output"
        )
        
        # Create mock base file
        (tmp_path / "base.mph").touch()
        cad_file = tmp_path / "test.step"
        
        runner.run_batch(
            design_id="d1",
            parameters={'L': 10, 'R': 5},
            cad_file=cad_file
        )
        
        # Check calls
        assert mock_sub.called
        args = mock_sub.call_args[0][0]
        
        assert args[0] == "/usr/local/bin/comsol"
        assert args[1] == "batch"
        assert "-input" in args
        assert "-pname" in args
        assert "L,R,cad_path,design_id" in args[args.index("-pname") + 1]
