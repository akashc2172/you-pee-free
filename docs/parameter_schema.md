# Stent Parameter Schema

## Overview

This document defines the current parameter space for stent design optimization. **11 parameters are sampled** via LHS in the active pipeline; coil geometry is fixed for this campaign stage.

## Sampling Strategy

- Sample **fractions** (r_t, r_sh, r_end) instead of absolute dimensions
- Derive wall_thickness, hole diameters from OD/ID
- Oversample ~3× and reject invalid rows before fitting GP
- All dimensions normalized to [0,1] for GP training

---

## Sampled Parameters (11 dimensions)

| # | Name | Unit | Range |
|---|------|------|-------|
| 1 | `stent_french` | Fr | [4.0, 8.0] |
| 2 | `stent_length` | mm | [100, 300] |
| 3 | `r_t` | - | [0.10, 0.22] |
| 4 | `r_sh` | - | [0.20, 0.70] |
| 5 | `r_end` | - | [0.30, 0.95] |
| 6 | `n_prox` | count | [0, 10] |
| 7 | `n_mid` | count | [0, 15] |
| 8 | `n_dist` | count | [0, 10] |
| 9 | `section_length_prox` | mm | [20, 60] |
| 10 | `section_length_dist` | mm | [20, 60] |
| 11 | `unroofed_length` | mm | [0, 30] |

## Fixed CAD Settings (Not Sampled)

- `freeze_coil_geometry = true`
- coil radius / helix pitch / helix turns are locked internally for v1
- `half_open_distal_enabled = true`
- `coil_hole_radius_mode = match_body_hole_radius`

---

## Derived Parameters

| Symbol | Formula | Description |
|--------|---------|-------------|
| wall_thickness | `r_t × (OD - ID) / 2` | Actual wall thickness |
| d_sh | `r_sh × (derived max)` | Side hole diameter |
| d_end | `r_end × (derived max)` | End hole diameter |
| pitch_min | `d_sh + gap_min` | Minimum center-to-center hole spacing |
| buffer | `max(1.0, d_sh)` | End clearance from section boundaries |
| L_use_prox | `L_prox - 2×buffer` | Usable length for holes (proximal) |
| L_use_mid | `L_mid - 2×buffer` | Usable length for holes (middle) |
| L_use_dist | `L_dist - 2×buffer` | Usable length for holes (distal) |
| requested_body_holes | `n_sh_prox + n_sh_mid + n_sh_dist` | Requested body-hole count |
| realized_body_holes | post-process | Realized body-hole count after unroofed rebalance |

---

## Hard Constraints (Feasibility Filtering)

Constraints are checked post-LHS sampling. Invalid designs are rejected before COMSOL runs.

| Constraint | Rule | Rejection Criteria |
|------------|------|-------------------|
| **ID_min** | ID ≥ 0.6 mm | Reject if ID < 0.6 |
| **gap_min** | Gap ≥ 0.3 mm | `pitch_min = d_sh + gap_min` |
| **buffer** | Clearance ≥ max(1.0, d_sh) | `L_use = L_section − 2×buffer` |
| **section_middle_min** | Middle section ≥ 10 mm | Reject if L_mid < 10 |
| **hole_packing** | `n_holes × pitch_min ≤ L_use` | Per section: prox, mid, dist |
| **wall_thickness_min** | wall ≥ [TBD] mm | Manufacturing constraint |
| **hole_diameter_max** | d_sh ≤ [TBD] × wall | Structural integrity |

### Feasibility Check Algorithm

```python
def is_feasible(params):
    # Hard min constraints
    if params['ID'] < 0.6: return False
    if params['L_mid'] < 10: return False
    
    # Derived values
    wall = params['r_t'] * (params['OD'] - params['ID']) / 2
    d_sh = params['r_sh'] * derive_max_hole_dia(params)  # TBD formula
    pitch_min = d_sh + 0.3  # gap_min
    buffer = max(1.0, d_sh)
    
    # Section packing checks
    for section in ['prox', 'mid', 'dist']:
        L_section = params[f'L_{section}']
        L_use = L_section - 2*buffer
        n_holes = params[f'n_sh_{section}']
        if n_holes * pitch_min > L_use:
            return False
    
    # Additional constraints TBD
    return True
```

---

## Parameter Interactions

Key interaction effects to investigate:

1. **Side hole impact depends on lumen/ID**: Flow through side holes may vary significantly with ID
2. **Hole placement × hole count**: More holes with tight spacing vs fewer with wider spacing
3. **Section length ratios**: Trade-off between prox/mid/dist flow distribution
4. **Wall thickness × hole diameter**: Structural vs flow trade-off
5. **Total length × hole pattern**: Longer stents allow more complex patterns

---

## Open Questions

- [ ] Finalize exact ranges for each parameter (coordinate with Parnian on COMSOL feasibility)
- [ ] Confirm gap_min = 0.3 mm (manufacturing constraint?)
- [ ] Define `derive_max_hole_dia()` formula based on structural constraints
- [ ] Add any additional hard constraints (e.g., minimum wall thickness for manufacturability)
- [ ] Confirm section count (3-section design: prox/mid/dist) or consider alternatives

---

## Requested vs Realized Hole Features

When `unroofed_length > 0`, CAD applies an automatic distal-hole rebalance rule:
- policy: `auto_rebalance`
- clearance from unroof boundary: `max(buffer_min, hole_radius)`
- holes in unroofed/clearance zones are suppressed and distal holes are redistributed within legal distal interval

Result columns (campaign manifests before COMSOL):
- `requested_n_prox/n_mid/n_dist`
- `precomsol_n_prox/n_mid/n_dist`
- `requested_midsection_hole_count`
- `precomsol_midsection_hole_count`
- `requested_body_holes`
- `precomsol_body_holes`
- `precomsol_total_hole_area`
- `precomsol_nearest_neighbor_spacing`
- `precomsol_arc_positions`
- `suppressed_holes_due_to_unroofed`
- `suppressed_holes_due_to_clearance`

Production `realized_*` columns remain present for schema stability, but they should stay null in the manifest until COMSOL exports them from the solved model.

COMSOL run columns (batch results):
- `sim_contract_version`
- `domain_template`
- `selection_strategy`
- `run_status`
- `failure_class`
- `qc_fail_reasons`
- `mass_imbalance`
- `mesh_min_quality`
- `parsed_realized_geometry_file`

Training feature rule:
- prefer realized hole-count columns when present
- fallback to requested columns for legacy data

Migration compatibility:
- older runs without realized columns remain valid by defaulting realized=requested.

---

## References

- See `stent_comsol_tracker.xlsx` → "Parameter Reference" sheet for constraint details
- See `gpr_sampling_meeting.pptx` → Slide 5 for feasibility constraint table
