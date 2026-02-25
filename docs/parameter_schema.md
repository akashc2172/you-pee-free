# Stent Parameter Schema

## Overview

This document defines the parameter space for stent design optimization. **14 parameters are sampled** via LHS, which reduce to **~12 effective dimensions** after feasibility constraints are applied.

## Sampling Strategy

- Sample **fractions** (r_t, r_sh, r_end) instead of absolute dimensions
- Derive wall_thickness, hole diameters from OD/ID
- Oversample ~3× and reject invalid rows before fitting GP
- All dimensions normalized to [0,1] for GP training

---

## Sampled Parameters (14 dimensions)

| # | Symbol | Name | Unit | Range | Description |
|---|--------|------|------|-------|-------------|
| 1 | OD | Outer Diameter | mm | [TBD] | Total stent outer diameter |
| 2 | ID | Inner Diameter | mm | [0.6, TBD] | Lumen diameter |
| 3 | L_total | Total Length | mm | [TBD] | Overall stent length |
| 4 | L_prox | Proximal Section Length | mm | fraction of L_total | Inlet section |
| 5 | L_mid | Middle Section Length | mm | fraction of L_total | Central section |
| 6 | L_dist | Distal Section Length | mm | fraction of L_total | Outlet section |
| 7 | r_t | Wall Thickness Ratio | - | [0,1] | fraction: wall = r_t × (OD-ID)/2 |
| 8 | r_sh | Side Hole Diameter Ratio | - | [0,1] | fraction of available space |
| 9 | r_end | End Hole Diameter Ratio | - | [0,1] | fraction for proximal/distal holes |
| 10 | n_sh_prox | # Proximal Side Holes | count | [0-10] | Number of side holes in proximal |
| 11 | n_sh_mid | # Middle Side Holes | count | [0-15] | Number of side holes in middle |
| 12 | n_sh_dist | # Distal Side Holes | count | [0-10] | Number of side holes in distal |
| 13 | pitch_ratio | Hole Pitch Ratio | - | [TBD] | Normalized spacing between holes |
| 14 | alpha | Hole Angle/Pattern | degrees or - | [TBD] | Angular placement pattern |

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

Result columns (campaign manifests):
- `requested_n_prox/n_mid/n_dist`
- `realized_n_prox/n_mid/n_dist`
- `requested_body_holes`, `realized_body_holes`
- `suppressed_holes_due_to_unroofed`
- `suppressed_holes_due_to_clearance`

Training feature rule:
- prefer realized hole-count columns when present
- fallback to requested columns for legacy data

Migration compatibility:
- older runs without realized columns remain valid by defaulting realized=requested.

---

## References

- See `stent_comsol_tracker.xlsx` → "Parameter Reference" sheet for constraint details
- See `gpr_sampling_meeting.pptx` → Slide 5 for feasibility constraint table
