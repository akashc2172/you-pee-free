# Hole Metadata Viewer

This viewer is for checking whether the exported hole-center points, normal vectors, and extraction measurement features actually make sense relative to the stent geometry.

It is a post-analysis tool. It does not require COMSOL and does not change the CAD or baseline COMSOL workflow.

Outputs:
- one simple `.html` viewer with a single rotatable 3D scene
- one `.glb` mesh sidecar kept mainly for archival/debug use

The viewer shows:
- the stent mesh in one rotatable 3D view
- every exported hole-center point
- every exported normal vector
- the canonical body axis
- measurement features from `*.meters.json` when available:
  - hole caps
  - distal lumen / annulus cross-sections
  - unroof patch
  - pressure refs listed in the side panel

## Script

- [export_hole_metadata_viewer.py](/Users/akashc/masters/scripts/export_hole_metadata_viewer.py)

## Python module

- [hole_metadata_viewer.py](/Users/akashc/masters/src/visualization/hole_metadata_viewer.py)

## Example

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/export_hole_metadata_viewer.py \
  --step /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.step \
  --holes_json /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.holes.json \
  --meters_json /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.meters.json \
  --output_dir /Users/akashc/masters/data/campaigns/campaign_len140/cad/viewer
```

Shaft-only:

```bash
PYTHONPATH=/Users/akashc/masters python3 scripts/export_hole_metadata_viewer.py \
  --step /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.step \
  --holes_json /Users/akashc/masters/data/campaigns/campaign_len140/cad/design_0000.holes.json \
  --output_dir /Users/akashc/masters/data/campaigns/campaign_len140/cad/viewer \
  --shaft_only
```

## Notes

- The model bytes are embedded directly into the HTML, so the page does not need to fetch a separate `.glb` file at runtime.
- The page is intentionally simple: one rotatable view, one legend, and one file summary.
- Auto-rotate is intentionally disabled.
- `*.meters.json` is auto-detected if it sits next to `*.holes.json`, so passing `--meters_json` is optional.
