"""Mesh quality checks for STL artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


@dataclass
class MeshQualityReport:
    watertight: bool
    is_winding_consistent: bool
    is_volume: bool
    n_vertices: int
    n_faces: int
    euler_number: int
    non_manifold_edges: int
    degenerate_faces: int
    self_intersection_suspected: bool
    passed: bool
    fail_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "watertight": self.watertight,
            "is_winding_consistent": self.is_winding_consistent,
            "is_volume": self.is_volume,
            "n_vertices": self.n_vertices,
            "n_faces": self.n_faces,
            "euler_number": self.euler_number,
            "non_manifold_edges": self.non_manifold_edges,
            "degenerate_faces": self.degenerate_faces,
            "self_intersection_suspected": self.self_intersection_suspected,
            "passed": self.passed,
            "fail_reasons": self.fail_reasons,
        }


def validate_stl(path: Path) -> MeshQualityReport:
    """Validate an STL mesh for import reliability."""
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError(
            "trimesh is required for STL QA. Install project dependencies with trimesh enabled."
        ) from exc

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"STL not found: {path}")

    # `process=True` is important here: it repairs obvious issues and populates
    # derived adjacency structures that QA relies on (watertightness, edge incidence).
    mesh = trimesh.load_mesh(str(path), file_type="stl", process=True, force="mesh")
    if mesh is None:
        raise ValueError(f"Failed to parse STL mesh: {path}")

    n_vertices = int(len(mesh.vertices))
    n_faces = int(len(mesh.faces))

    if n_faces == 0:
        raise ValueError(f"Mesh contains no faces: {path}")

    # Edge incidence counts from face->edge mapping.
    non_manifold_edges = 0
    if hasattr(mesh, "faces_unique_edges") and hasattr(mesh, "edges_unique"):
        edge_ids = np.asarray(mesh.faces_unique_edges).reshape(-1)
        edge_counts = np.bincount(edge_ids, minlength=len(mesh.edges_unique))
        non_manifold_edges = int(np.sum(edge_counts > 2))

    # Degenerate triangles via area threshold.
    tri_areas = np.asarray(mesh.area_faces)
    degenerate_faces = int(np.sum(tri_areas <= 1e-16))

    watertight = bool(mesh.is_watertight)
    is_winding_consistent = bool(mesh.is_winding_consistent)
    is_volume = bool(mesh.is_volume)
    euler_number = int(mesh.euler_number)

    # Heuristic signal, since robust self-intersection checks are expensive.
    self_intersection_suspected = bool(
        (not watertight and non_manifold_edges > 0) or degenerate_faces > 0
    )

    fail_reasons: List[str] = []
    if not watertight:
        fail_reasons.append("not watertight")
    if not is_winding_consistent:
        fail_reasons.append("inconsistent winding")
    if not is_volume:
        fail_reasons.append("not a closed volume")
    if non_manifold_edges > 0:
        fail_reasons.append(f"non-manifold edges={non_manifold_edges}")
    if degenerate_faces > 0:
        fail_reasons.append(f"degenerate faces={degenerate_faces}")
    if self_intersection_suspected:
        fail_reasons.append("self-intersection suspected")

    passed = len(fail_reasons) == 0

    return MeshQualityReport(
        watertight=watertight,
        is_winding_consistent=is_winding_consistent,
        is_volume=is_volume,
        n_vertices=n_vertices,
        n_faces=n_faces,
        euler_number=euler_number,
        non_manifold_edges=non_manifold_edges,
        degenerate_faces=degenerate_faces,
        self_intersection_suspected=self_intersection_suspected,
        passed=passed,
        fail_reasons=fail_reasons,
    )
