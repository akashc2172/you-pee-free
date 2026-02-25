"""Tests for STL mesh-quality validation."""

from pathlib import Path

import pytest

from src.cad.mesh_quality import validate_stl

trimesh = pytest.importorskip("trimesh")


def _write_mesh(path: Path, vertices, faces):
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(path)


def test_validate_stl_valid_stent_like_mesh(tmp_path: Path):
    """Closed meshes should pass QA checks."""
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    path = tmp_path / "box.stl"
    mesh.export(path)

    report = validate_stl(path)
    assert report.passed is True
    assert report.watertight is True
    assert report.non_manifold_edges == 0
    assert report.degenerate_faces == 0


def test_validate_stl_detects_specific_failures(tmp_path: Path):
    """Open single-triangle mesh should fail with concrete reasons."""
    path = tmp_path / "open_triangle.stl"
    vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    faces = [[0, 1, 2]]
    _write_mesh(path, vertices, faces)

    report = validate_stl(path)
    assert report.passed is False
    assert any("not watertight" in r for r in report.fail_reasons)


def test_validate_stl_detects_degenerate_faces(tmp_path: Path):
    """Degenerate faces should be counted and fail QA."""
    path = tmp_path / "degenerate.stl"
    vertices = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    faces = [[0, 0, 1]]
    _write_mesh(path, vertices, faces)

    report = validate_stl(path)
    assert report.passed is False
    assert report.degenerate_faces > 0


def test_validate_stl_detects_non_manifold_edges(tmp_path: Path):
    """Edge shared by >2 faces should be detected as non-manifold."""
    path = tmp_path / "nonmanifold.stl"
    vertices = [
        [0, 0, 0],  # shared edge
        [1, 0, 0],  # shared edge
        [0, 1, 0],
        [0, 0, 1],
        [0, -1, 0],
    ]
    faces = [
        [0, 1, 2],
        [0, 1, 3],
        [0, 1, 4],
    ]
    _write_mesh(path, vertices, faces)

    report = validate_stl(path)
    assert report.passed is False
    assert report.non_manifold_edges > 0
