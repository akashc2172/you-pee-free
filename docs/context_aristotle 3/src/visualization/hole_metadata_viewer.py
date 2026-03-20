"""
Generate a simple single-view HTML viewer for stent hole and measurement metadata.

The HTML embeds lightweight mesh + metadata JSON directly and renders it with a
plain local three.js viewer, avoiding module/CDN/GLTF runtime issues.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import trimesh
from build123d import export_stl, import_step


TYPE_COLORS = {
    "shaft": "#2d7db3",
    "coil": "#d98a1f",
}

FEATURE_COLORS = {
    "hole_cap": "#7f56d9",
    "cross_section": "#0ea5a4",
    "unroof_patch": "#d9485f",
    "pressure_ref": "#6b7280",
}

STENT_COLOR = "#d9cbb7"
AXIS_COLOR = "#8c8f94"
MAX_HTML_FACES = 30000


def load_hole_metadata(path: Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    holes = payload.get("holes", [])
    if not isinstance(holes, list):
        raise ValueError("invalid_hole_metadata: holes must be a list")
    return payload


def load_measurement_metadata(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text())
    features = payload.get("features", [])
    if not isinstance(features, list):
        raise ValueError("invalid_measurement_metadata: features must be a list")
    return payload


def load_step_as_trimesh(step_path: Path) -> trimesh.Trimesh:
    step_path = Path(step_path)
    shape = import_step(step_path)
    with tempfile.TemporaryDirectory(prefix="stent_step_mesh_") as tmpdir:
        stl_path = Path(tmpdir) / f"{step_path.stem}.stl"
        export_stl(
            shape,
            str(stl_path),
            tolerance=0.01,
            angular_tolerance=0.1,
            ascii_format=False,
        )
        mesh = trimesh.load_mesh(stl_path, force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"unsupported_mesh_type: {type(mesh)}")
    return mesh


def _unit_vector(values: Iterable[float]) -> np.ndarray:
    arr = np.array([float(v) for v in values], dtype=float)
    mag = np.linalg.norm(arr)
    if mag <= 1e-12:
        return np.array([1.0, 0.0, 0.0], dtype=float)
    return arr / mag


def _rgba(hex_color: str, alpha: int = 255) -> np.ndarray:
    hex_color = hex_color.lstrip("#")
    return np.array(
        [
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
            int(alpha),
        ],
        dtype=np.uint8,
    )


def _apply_color(mesh: trimesh.Trimesh, rgba: np.ndarray) -> trimesh.Trimesh:
    mesh.visual.face_colors = np.tile(rgba, (len(mesh.faces), 1))
    return mesh


def _plane_transform(center: Sequence[float], normal: Sequence[float]) -> np.ndarray:
    tf = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], _unit_vector(normal))
    tf = np.array(tf, dtype=float)
    tf[:3, 3] = np.array([float(v) for v in center], dtype=float)
    return tf


def _build_arrow_mesh(
    start: Sequence[float],
    direction: Sequence[float],
    length: float,
    color_hex: str,
    shaft_radius: float = 0.12,
    head_radius: float = 0.28,
    head_length: float = 0.9,
) -> trimesh.Trimesh:
    start_vec = np.array([float(v) for v in start], dtype=float)
    direction_vec = _unit_vector(direction)
    if length <= head_length + 1e-6:
        length = head_length + 0.5
    shaft_end = start_vec + direction_vec * (length - head_length)
    arrow_tip = start_vec + direction_vec * length

    shaft = trimesh.creation.cylinder(
        radius=shaft_radius,
        segment=[start_vec.tolist(), shaft_end.tolist()],
        sections=18,
    )
    shaft = _apply_color(shaft, _rgba(color_hex, 255))

    cone_transform = _plane_transform(shaft_end.tolist(), direction_vec.tolist())
    cone = trimesh.creation.cone(
        radius=head_radius,
        height=head_length,
        sections=18,
        transform=cone_transform,
    )
    cone = _apply_color(cone, _rgba(color_hex, 255))

    return trimesh.util.concatenate([shaft, cone])


def _build_measurement_mesh(feature: Dict[str, Any]) -> Optional[trimesh.Trimesh]:
    geometry_type = str(feature.get("geometry_type", ""))
    feature_class = str(feature.get("feature_class", ""))
    color = FEATURE_COLORS.get(feature_class, "#666666")

    if geometry_type == "named_selection":
        return None

    center = feature.get("center_mm")
    normal = feature.get("normal")
    if not isinstance(center, list) or len(center) != 3:
        return None

    normal_vec = [0.0, 0.0, 1.0]
    if isinstance(normal, list) and len(normal) == 3:
        normal_vec = [float(v) for v in normal]

    if geometry_type == "cutplane_disk":
        radius = float(feature.get("radius_mm", 0.0))
        if radius <= 0.0:
            return None
        mesh = trimesh.creation.cylinder(
            radius=radius,
            height=0.14,
            sections=32,
            transform=_plane_transform(center, normal_vec),
        )
        return _apply_color(mesh, _rgba(color, 125))

    if geometry_type == "cutplane_annulus":
        r_min = float(feature.get("inner_radius_mm", 0.0))
        r_max = float(feature.get("outer_radius_mm", 0.0))
        if r_max <= 0.0 or r_max <= r_min:
            return None
        mesh = trimesh.creation.annulus(
            r_min=r_min,
            r_max=r_max,
            height=0.14,
            sections=32,
            transform=_plane_transform(center, normal_vec),
        )
        return _apply_color(mesh, _rgba(color, 125))

    if geometry_type == "cutplane_rect":
        x_half = float(feature.get("x_half_width_mm", 0.0))
        z_half = float(feature.get("z_half_width_mm", 0.0))
        if x_half <= 0.0 or z_half <= 0.0:
            return None
        mesh = trimesh.creation.box(extents=[2.0 * x_half, 2.0 * z_half, 0.14])
        mesh.apply_transform(_plane_transform(center, normal_vec))
        return _apply_color(mesh, _rgba(color, 115))

    return None


def _filter_holes(metadata: Dict[str, Any], show_shaft: bool, show_coil: bool) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for hole in metadata.get("holes", []):
        hole_type = str(hole.get("type", ""))
        if hole_type == "shaft" and not show_shaft:
            continue
        if hole_type == "coil" and not show_coil:
            continue
        filtered.append(hole)
    return filtered


def _filter_features(
    measurement_metadata: Optional[Dict[str, Any]],
    visible_hole_ids: set[str],
) -> List[Dict[str, Any]]:
    if measurement_metadata is None:
        return []
    kept: List[Dict[str, Any]] = []
    for feature in measurement_metadata.get("features", []):
        if str(feature.get("feature_class", "")) == "hole_cap":
            parent = str(feature.get("parent_feature", ""))
            if parent and parent not in visible_hole_ids:
                continue
        kept.append(feature)
    return kept


def _measurement_summary(measurement_metadata: Optional[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"hole_cap": 0, "cross_section": 0, "unroof_patch": 0, "pressure_ref": 0}
    if measurement_metadata is None:
        return counts
    for feature in measurement_metadata.get("features", []):
        feature_class = str(feature.get("feature_class", ""))
        if feature_class in counts:
            counts[feature_class] += 1
    return counts


def _downsample_mesh(mesh: trimesh.Trimesh, max_faces: int = MAX_HTML_FACES) -> trimesh.Trimesh:
    mesh = mesh.copy()
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces) <= max_faces:
        return mesh

    step = max(1, int(math.ceil(len(mesh.faces) / float(max_faces))))
    keep_faces = mesh.faces[::step][:max_faces]
    used = np.unique(keep_faces.reshape(-1))
    remap = {int(old): idx for idx, old in enumerate(used.tolist())}
    new_vertices = mesh.vertices[used]
    flat_faces = []
    for tri in keep_faces:
        flat_faces.append([remap[int(tri[0])], remap[int(tri[1])], remap[int(tri[2])]])
    reduced = trimesh.Trimesh(vertices=new_vertices, faces=np.array(flat_faces), process=False)
    reduced.remove_unreferenced_vertices()
    return reduced


def _build_scene_payload(
    metadata: Dict[str, Any],
    measurement_metadata: Optional[Dict[str, Any]],
    mesh: trimesh.Trimesh,
    show_shaft: bool,
    show_coil: bool,
) -> Dict[str, Any]:
    holes = _filter_holes(metadata, show_shaft=show_shaft, show_coil=show_coil)
    visible_hole_ids = {str(hole.get("hole_id", "")) for hole in holes}
    features = _filter_features(measurement_metadata, visible_hole_ids)
    preview_mesh = _downsample_mesh(mesh)

    payload = {
        "stent": {
            "vertices": [[float(v) for v in row] for row in preview_mesh.vertices.tolist()],
            "faces": [[int(v) for v in row] for row in preview_mesh.faces.tolist()],
            "color": STENT_COLOR,
            "opacity": 0.82,
        },
        "axis": {
            "start": [float(metadata.get("export_body_start_x_mm", 0.0)), 0.0, 0.0],
            "end": [float(metadata.get("export_body_end_x_mm", 10.0)), 0.0, 0.0],
            "radius": max(0.06, float(metadata.get("r_outer_mm", 1.0)) * 0.08),
            "color": AXIS_COLOR,
        },
        "holes": [],
        "features": [],
    }

    r_outer = float(metadata.get("r_outer_mm", 1.0))
    for hole in holes:
        hole_type = str(hole.get("type", "shaft"))
        payload["holes"].append(
            {
                "hole_id": str(hole.get("hole_id", "")),
                "type": hole_type,
                "center": [float(v) for v in hole["center_mm"]],
                "normal": [float(v) for v in hole["normal"]],
                "color": TYPE_COLORS.get(hole_type, "#666666"),
                "point_radius": max(0.18, r_outer * 0.22),
                "normal_length": max(3.8, r_outer * 3.6),
                "normal_radius": max(0.06, r_outer * 0.07),
                "head_radius": max(0.18, r_outer * 0.16),
            }
        )

    for feature in features:
        item = {
            "feature_id": str(feature.get("feature_id", "")),
            "feature_class": str(feature.get("feature_class", "")),
            "geometry_type": str(feature.get("geometry_type", "")),
            "color": FEATURE_COLORS.get(str(feature.get("feature_class", "")), "#666666"),
        }
        if isinstance(feature.get("center_mm"), list):
            item["center"] = [float(v) for v in feature["center_mm"]]
        if isinstance(feature.get("normal"), list):
            item["normal"] = [float(v) for v in feature["normal"]]
        for key in ("radius_mm", "inner_radius_mm", "outer_radius_mm", "x_half_width_mm", "z_half_width_mm"):
            if key in feature:
                item[key] = float(feature[key])
        payload["features"].append(item)

    return payload


def build_hole_viewer_scene(
    metadata: Dict[str, Any],
    mesh: trimesh.Trimesh,
    measurement_metadata: Optional[Dict[str, Any]] = None,
    show_shaft: bool = True,
    show_coil: bool = True,
) -> trimesh.Scene:
    scene = trimesh.Scene()

    holes = _filter_holes(metadata, show_shaft=show_shaft, show_coil=show_coil)
    visible_hole_ids = {str(hole.get("hole_id", "")) for hole in holes}
    features = _filter_features(measurement_metadata, visible_hole_ids)

    stent_mesh = mesh.copy()
    _apply_color(stent_mesh, _rgba(STENT_COLOR, 210))
    scene.add_geometry(stent_mesh, node_name="stent_mesh")

    body_start = float(metadata.get("export_body_start_x_mm", 0.0))
    body_end = float(metadata.get("export_body_end_x_mm", body_start + 10.0))
    r_outer = float(metadata.get("r_outer_mm", 1.0))

    axis = trimesh.creation.cylinder(
        radius=max(0.06, r_outer * 0.08),
        segment=[[body_start, 0.0, 0.0], [body_end, 0.0, 0.0]],
        sections=16,
    )
    _apply_color(axis, _rgba(AXIS_COLOR, 255))
    scene.add_geometry(axis, node_name="body_axis")

    point_radius = max(0.18, r_outer * 0.22)
    normal_length = max(3.8, r_outer * 3.6)
    normal_shaft_radius = max(0.06, r_outer * 0.07)
    normal_head_radius = max(0.18, r_outer * 0.16)

    for hole in holes:
        hole_id = str(hole.get("hole_id", "hole"))
        center = [float(v) for v in hole["center_mm"]]
        normal = [float(v) for v in hole["normal"]]
        hole_type = str(hole.get("type", "shaft"))
        color = TYPE_COLORS.get(hole_type, "#666666")

        point = trimesh.creation.icosphere(subdivisions=2, radius=point_radius)
        point.apply_translation(center)
        _apply_color(point, _rgba(color, 255))
        scene.add_geometry(point, node_name=f"{hole_id}_point")

        arrow = _build_arrow_mesh(
            start=center,
            direction=normal,
            length=normal_length,
            color_hex=color,
            shaft_radius=normal_shaft_radius,
            head_radius=normal_head_radius,
            head_length=max(0.8, normal_length * 0.22),
        )
        scene.add_geometry(arrow, node_name=f"{hole_id}_normal")

    for feature in features:
        feature_id = str(feature.get("feature_id", "feature"))
        feature_mesh = _build_measurement_mesh(feature)
        if feature_mesh is not None:
            scene.add_geometry(feature_mesh, node_name=feature_id)

    return scene


def write_viewer_html(
    html_path: Path,
    step_filename: str,
    holes_filename: str,
    meters_filename: Optional[str],
    metadata: Dict[str, Any],
    measurement_metadata: Optional[Dict[str, Any]],
    mesh: trimesh.Trimesh,
    show_shaft: bool,
    show_coil: bool,
) -> None:
    design_id = str(metadata.get("design_id", html_path.stem))
    holes = _filter_holes(metadata, show_shaft=show_shaft, show_coil=show_coil)
    features = _filter_features(
        measurement_metadata,
        {str(hole.get("hole_id", "")) for hole in holes},
    )
    feature_counts = _measurement_summary({"features": features} if measurement_metadata is not None else None)

    payload = _build_scene_payload(
        metadata=metadata,
        measurement_metadata=measurement_metadata,
        mesh=mesh,
        show_shaft=show_shaft,
        show_coil=show_coil,
    )
    payload_json = json.dumps(payload, separators=(",", ":"))

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{design_id} Viewer</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f4f1ec;
      color: #2d2a26;
    }}
    .wrap {{
      display: grid;
      grid-template-columns: 330px 1fr;
      min-height: 100vh;
    }}
    .side {{
      background: #fcfaf6;
      border-right: 1px solid #dfd7cd;
      padding: 20px 18px;
    }}
    .side h1 {{
      margin: 0 0 10px;
      font-size: 22px;
      line-height: 1.15;
    }}
    .side p {{
      margin: 8px 0;
      line-height: 1.45;
    }}
    .legend {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 8px 0;
    }}
    .sw {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      border: 1px solid rgba(0,0,0,0.15);
      flex: 0 0 auto;
    }}
    .main {{ padding: 16px; }}
    .viewer-card {{
      background: #fffdf8;
      border: 1px solid #dfd7cd;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      height: calc(100vh - 32px);
      min-height: 720px;
      position: relative;
    }}
    #c {{
      width: 100%;
      height: 100%;
      display: block;
      background: radial-gradient(circle at 30% 20%, #fffdf9 0%, #f3eee6 55%, #ece5da 100%);
    }}
    .hud {{
      position: absolute;
      left: 12px;
      bottom: 12px;
      background: rgba(252, 250, 246, 0.88);
      border: 1px solid rgba(223, 215, 205, 0.9);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 12px;
      color: #4b453e;
    }}
    code {{
      background: #f0ebe2;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12px;
    }}
    .small {{
      color: #655f58;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="side">
      <h1>{design_id}</h1>
      <p><strong>Offline rotatable metadata check</strong></p>
      <p>Total visible holes: <strong>{len(holes)}</strong></p>
      <p>Shaft shown: <strong>{str(show_shaft).lower()}</strong></p>
      <p>Coil shown: <strong>{str(show_coil).lower()}</strong></p>
      <p class="small">Drag to rotate. Wheel to zoom. Right-drag to pan. No auto-rotate and no inertial spin.</p>
      <p><strong>Legend</strong></p>
      <div class="legend"><span class="sw" style="background:{STENT_COLOR}"></span><span>Stent</span></div>
      <div class="legend"><span class="sw" style="background:{TYPE_COLORS['shaft']}"></span><span>Shaft hole point + normal</span></div>
      <div class="legend"><span class="sw" style="background:{TYPE_COLORS['coil']}"></span><span>Coil hole point + normal</span></div>
      <div class="legend"><span class="sw" style="background:{FEATURE_COLORS['hole_cap']}"></span><span>Hole caps</span></div>
      <div class="legend"><span class="sw" style="background:{FEATURE_COLORS['cross_section']}"></span><span>Cross-sections</span></div>
      <div class="legend"><span class="sw" style="background:{FEATURE_COLORS['unroof_patch']}"></span><span>Unroof patch</span></div>
      <p><strong>Measurement counts</strong></p>
      <p>Hole caps: <strong>{feature_counts['hole_cap']}</strong></p>
      <p>Cross-sections: <strong>{feature_counts['cross_section']}</strong></p>
      <p>Unroof patches: <strong>{feature_counts['unroof_patch']}</strong></p>
      <p>Pressure refs: <strong>{feature_counts['pressure_ref']}</strong></p>
      <p><strong>Files</strong></p>
      <p><code>{step_filename}</code></p>
      <p><code>{holes_filename}</code></p>
      <p><code>{meters_filename if meters_filename is not None else 'none'}</code></p>
    </div>
    <div class="main">
      <div class="viewer-card">
        <canvas id="c"></canvas>
        <div class="hud">Left drag: rotate · Wheel: zoom · Right drag: pan</div>
      </div>
    </div>
  </div>

  <script src="./vendor/three.min.js"></script>
  <script src="./vendor/OrbitControls.legacy.js"></script>
  <script>
    var VIEWER_DATA = {payload_json};
  </script>
  <script>
    var canvas = document.getElementById('c');
    var renderer = new THREE.WebGLRenderer({{ canvas: canvas, antialias: true, alpha: true }});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    // Color management varies across three.js versions.
    if ('outputColorSpace' in renderer && THREE.SRGBColorSpace) {{
      renderer.outputColorSpace = THREE.SRGBColorSpace;
    }} else if ('outputEncoding' in renderer && THREE.sRGBEncoding) {{
      renderer.outputEncoding = THREE.sRGBEncoding;
    }}

    var scene = new THREE.Scene();
    scene.background = null;

    var camera = new THREE.PerspectiveCamera(35, 2, 0.1, 10000);
    camera.position.set(240, 120, 120);

    var controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = false;   // no inertial spin
    controls.autoRotate = false;      // no auto-rotate
    controls.enablePan = true;
    controls.screenSpacePanning = true;

    var hemi = new THREE.HemisphereLight(0xffffff, 0x5b5146, 0.85);
    scene.add(hemi);
    var dir = new THREE.DirectionalLight(0xffffff, 0.85);
    dir.position.set(250, 240, 180);
    scene.add(dir);

    function setHud(message) {{
      document.querySelector('.hud').textContent = message;
    }}

    window.addEventListener('error', function (event) {{
      setHud('Viewer error: ' + event.message);
    }});

    function hexToColor(hex) {{
      return new THREE.Color(hex);
    }}

    function toVec3(vals) {{
      return new THREE.Vector3(vals[0], vals[1], vals[2]);
    }}

    function unitVec(vals) {{
      var v = toVec3(vals);
      if (v.length() < 1e-12) return new THREE.Vector3(1, 0, 0);
      return v.normalize();
    }}

    function addStentMesh(data) {{
      var geometry = new THREE.BufferGeometry();
      var positions = new Float32Array(data.vertices.length * 3);
      for (var i = 0; i < data.vertices.length; i += 1) {{
        positions[3 * i + 0] = data.vertices[i][0];
        positions[3 * i + 1] = data.vertices[i][1];
        positions[3 * i + 2] = data.vertices[i][2];
      }}
      var indices = new Uint32Array(data.faces.length * 3);
      for (var j = 0; j < data.faces.length; j += 1) {{
        indices[3 * j + 0] = data.faces[j][0];
        indices[3 * j + 1] = data.faces[j][1];
        indices[3 * j + 2] = data.faces[j][2];
      }}
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setIndex(new THREE.BufferAttribute(indices, 1));
      geometry.computeVertexNormals();
      var material = new THREE.MeshStandardMaterial({{
        color: hexToColor(data.color),
        roughness: 0.78,
        metalness: 0.0,
        transparent: true,
        opacity: data.opacity
      }});
      var mesh = new THREE.Mesh(geometry, material);
      mesh.name = 'stent_mesh';
      scene.add(mesh);
      return mesh;
    }}

    function addAxis(data) {{
      var geometry = new THREE.CylinderGeometry(data.radius, data.radius, 1, 16);
      var material = new THREE.MeshStandardMaterial({{
        color: hexToColor(data.color),
        roughness: 0.9,
        metalness: 0.0
      }});
      var axis = new THREE.Mesh(geometry, material);
      var start = toVec3(data.start);
      var end = toVec3(data.end);
      var dirv = end.clone().sub(start);
      var length = dirv.length();
      axis.scale.set(1, length, 1);
      axis.position.copy(start.clone().add(end).multiplyScalar(0.5));
      axis.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dirv.clone().normalize());
      scene.add(axis);
      return axis;
    }}

    function addArrow(centerVals, normalVals, colorHex, shaftRadius, headRadius, length) {{
      var group = new THREE.Group();
      var center = toVec3(centerVals);
      var dirv = unitVec(normalVals);
      var headLength = Math.max(0.8, length * 0.22);
      var shaftLength = Math.max(0.2, length - headLength);

      var shaftGeom = new THREE.CylinderGeometry(shaftRadius, shaftRadius, shaftLength, 16);
      var shaftMat = new THREE.MeshStandardMaterial({{ color: hexToColor(colorHex), roughness: 0.8, metalness: 0.0 }});
      var shaft = new THREE.Mesh(shaftGeom, shaftMat);
      shaft.position.y = shaftLength * 0.5;
      group.add(shaft);

      var headGeom = new THREE.ConeGeometry(headRadius, headLength, 16);
      var headMat = new THREE.MeshStandardMaterial({{ color: hexToColor(colorHex), roughness: 0.8, metalness: 0.0 }});
      var head = new THREE.Mesh(headGeom, headMat);
      head.position.y = shaftLength + headLength * 0.5;
      group.add(head);

      group.position.copy(center);
      group.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dirv);
      scene.add(group);
      return group;
    }}

    function addHole(hole) {{
      var sphereGeom = new THREE.SphereGeometry(hole.point_radius, 16, 16);
      var sphereMat = new THREE.MeshStandardMaterial({{ color: hexToColor(hole.color), roughness: 0.7, metalness: 0.0 }});
      var point = new THREE.Mesh(sphereGeom, sphereMat);
      point.position.copy(toVec3(hole.center));
      scene.add(point);
      addArrow(hole.center, hole.normal, hole.color, hole.normal_radius, hole.head_radius, hole.normal_length);
    }}

    function addFeature(feature) {{
      var material = new THREE.MeshStandardMaterial({{
        color: hexToColor(feature.color),
        roughness: 0.85,
        metalness: 0.0,
        transparent: true,
        opacity: 0.45,
        side: THREE.DoubleSide
      }});
      var mesh = null;
      if (feature.geometry_type === 'cutplane_disk') {{
        mesh = new THREE.Mesh(
          new THREE.CylinderGeometry(feature.radius_mm, feature.radius_mm, 0.14, 24),
          material
        );
      }} else if (feature.geometry_type === 'cutplane_annulus') {{
        var shape = new THREE.Shape();
        shape.absarc(0, 0, feature.outer_radius_mm, 0, Math.PI * 2, false);
        var hole = new THREE.Path();
        hole.absarc(0, 0, feature.inner_radius_mm, 0, Math.PI * 2, true);
        shape.holes.push(hole);
        mesh = new THREE.Mesh(
          new THREE.ExtrudeGeometry(shape, {{ depth: 0.14, bevelEnabled: false }}),
          material
        );
        mesh.position.z = -0.07;
      }} else if (feature.geometry_type === 'cutplane_rect') {{
        mesh = new THREE.Mesh(
          new THREE.BoxGeometry(feature.x_half_width_mm * 2, 0.14, feature.z_half_width_mm * 2),
          material
        );
      }}
      if (!mesh) return;
      if (feature.center) {{
        mesh.position.copy(toVec3(feature.center));
      }}
      if (feature.normal) {{
        mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), unitVec(feature.normal));
      }}
      scene.add(mesh);
    }}

    var stentObject = addStentMesh(VIEWER_DATA.stent);
    addAxis(VIEWER_DATA.axis);
    for (var h = 0; h < VIEWER_DATA.holes.length; h += 1) {{
      addHole(VIEWER_DATA.holes[h]);
    }}
    for (var f = 0; f < VIEWER_DATA.features.length; f += 1) {{
      addFeature(VIEWER_DATA.features[f]);
    }}

    var box = new THREE.Box3().setFromObject(stentObject);
    if (!box.isEmpty()) {{
      var center = new THREE.Vector3();
      var size = new THREE.Vector3();
      box.getCenter(center);
      box.getSize(size);
      controls.target.copy(center);
      var dist = Math.max(size.x, size.y, size.z) * 1.25;
      camera.position.set(center.x + dist, center.y + dist * 0.35, center.z + dist * 0.35);
      camera.near = Math.max(0.1, dist / 2000);
      camera.far = dist * 10;
      camera.updateProjectionMatrix();
      controls.update();
    }}
    setHud('Left drag: rotate · Wheel: zoom · Right drag: pan');

    function resize() {{
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w || canvas.height !== h) {{
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      }}
    }}

    function animate() {{
      resize();
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }}
    animate();

  </script>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")


def export_hole_metadata_viewer(
    step_path: Path,
    holes_json: Path,
    output_dir: Path,
    show_shaft: bool = True,
    show_coil: bool = True,
    meters_json: Optional[Path] = None,
) -> Dict[str, str]:
    step_path = Path(step_path)
    holes_json = Path(holes_json)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if meters_json is None:
        auto_meters = holes_json.parent / holes_json.name.replace(".holes.json", ".meters.json")
        if auto_meters.exists():
            meters_json = auto_meters

    metadata = load_hole_metadata(holes_json)
    measurement_metadata = load_measurement_metadata(meters_json)
    stent_mesh = load_step_as_trimesh(step_path)

    stem = step_path.stem
    suffix = "all_holes" if show_shaft and show_coil else "shaft_holes" if show_shaft else "coil_holes"
    glb_path = output_dir / f"{stem}_{suffix}_viewer.glb"
    html_path = output_dir / f"{stem}_{suffix}_viewer.html"

    # Ensure offline JS dependencies are available next to the HTML.
    vendor_src = Path(__file__).parent / "vendor"
    vendor_dst = output_dir / "vendor"
    vendor_dst.mkdir(parents=True, exist_ok=True)
    for name in ("three.min.js", "OrbitControls.legacy.js"):
        src = vendor_src / name
        if not src.exists():
            raise FileNotFoundError(f"missing_viewer_vendor_asset:{src}")
        shutil.copy2(src, vendor_dst / name)

    scene = build_hole_viewer_scene(
        metadata=metadata,
        mesh=stent_mesh,
        measurement_metadata=measurement_metadata,
        show_shaft=show_shaft,
        show_coil=show_coil,
    )
    glb_path.write_bytes(scene.export(file_type="glb"))

    write_viewer_html(
        html_path=html_path,
        step_filename=step_path.name,
        holes_filename=holes_json.name,
        meters_filename=None if meters_json is None else Path(meters_json).name,
        metadata=metadata,
        measurement_metadata=measurement_metadata,
        mesh=stent_mesh,
        show_shaft=show_shaft,
        show_coil=show_coil,
    )

    outputs = {
        "html": str(html_path),
        "glb": str(glb_path),
    }
    if meters_json is not None:
        outputs["meters_json"] = str(meters_json)
    return outputs
