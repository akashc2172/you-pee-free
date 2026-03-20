# Formal Specification: Stent Feature Selection, Feasibility, and Flux Aggregation

**Version:** 1.0  
**Date:** 2025-01-27  
**Scope:** CAD → COMSOL → CSV pipeline for pediatric ureteral stent geometry optimization  
**Status:** Implementation-ready specification  

---

## 1. Executive Recommendation

After inspecting the full repository—CAD generator (`stent_generator.py`), measurement-surface schema (`schema.py`), feasibility filter (`feasibility.py`), COMSOL Java extraction method (`BuildFluxExtractionLayer.java.txt`), postprocessing (`flux_extraction.py`), result parser (`result_parser.py`), runner (`runner.py`), both `.meters.json` and `.holes.json` sidecar examples, the `comsol_output_framework.md`, and the `parameters.yaml`—I make the following top-level recommendations:

1. **Zone assignment should use metadata-derived parent-region labels, not runtime geometric projection.** The current implementation already does this: zone is assigned at CAD generation time and stored in `*.meters.json`. This is the correct approach. A secondary audit rule should verify that `axial_x_mm` is consistent with the assigned zone's axial interval, and flag mismatches without overriding the metadata label.

2. **Feasibility filtering must be formalized beyond the current `StentParameters.__post_init__` delegation.** The current `FeasibilityFilter._check_row()` simply tries to instantiate `StentParameters` and catches `ValueError`. This is structurally sound but insufficient: it does not enforce unroof/hole collision geometry, does not validate that the distal cross-section plane lies within a valid region, and does not guard against degenerate coil-hole placements. A formal feasible-set specification is given below.

3. **The flux metric definitions in `flux_extraction.py` are largely correct but have three issues:**  
   - `hole_uniformity_cv` uses population stddev (`ddof=0`) which is acceptable but should be documented as a deliberate choice.  
   - The Gini metric (`hole_uniformity_gini`) is mentioned in `comsol_output_framework.md` but is not implemented anywhere in the codebase.  
   - The `frac_unroof_of_total` denominator uses `Q_out` (outlet flow) not `Q_exchange_total_abs` (sum of all exchange fluxes). These measure different things and must be distinguished clearly.

4. **The `COMSOLResult` dataclass in `result_parser.py` still uses legacy grouped outputs (`q_sh_prox/mid/dist`) whereas `flux_extraction.py` uses per-feature extraction.** These two paths should converge. The per-feature path is strictly more general and should become the primary.

5. **Coil-hole cap placement is explicitly flagged as provisional** in the metadata (`"cap_center_rule": "coil hole cap currently uses the exported coil-hole center/axis; dedicated coil-mouth reconstruction can refine this later"`). This is an honest limitation. I formalize conditions under which it remains acceptable and when it becomes a hard failure.

6. **Better derived metrics are warranted.** The current `prox/mid/dist` absolute hole flux decomposition discards axial localization information. I propose a flux-weighted axial centroid and a flux spread metric as superior replacements, while keeping zone-summed metrics for backward compatibility.

---

## 2. Formal Object Model

### 2.1 Core Objects

Objects are listed with **required** fields (must be present and non-null) and *optional* fields (useful but may be absent or null).

#### `Design`
| Field | Type | Required | Source |
|-------|------|----------|--------|
| `design_id` | `str` | **yes** | Generated at CAD time |
| `campaign_id` | `str` | **yes** | Campaign configuration |
| `stent_parameters` | `StentParameters` | **yes** | Sampled + derived |
| `measurement_package` | `MeasurementSurfacePackage` | **yes** | Generated at CAD time |
| `cad_file` | `Path` | **yes** | STEP export path |
| `holes_sidecar` | `Path` | **yes** | `.holes.json` |
| `meters_sidecar` | `Path` | **yes** | `.meters.json` |
| `sim_contract_version` | `str` | **yes** | From `parameters.yaml` |

#### `MeasurementFeature` (already exists in `schema.py`)
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `feature_id` | `str` | **yes** | Globally unique within a design |
| `feature_class` | `enum{hole_cap, unroof_patch, cross_section, pressure_ref}` | **yes** | |
| `zone` | `enum{prox, mid, dist}` | **yes** | |
| `geometry_type` | `enum{cutplane_disk, cutplane_annulus, cutplane_rect, named_selection}` | **yes** | |
| `center_mm` | `[float, float, float]` | **yes** unless `named_selection` | |
| `normal` | `[float, float, float]` | **yes** unless `named_selection` | Unit vector |
| `radius_mm` | `float` | Required for `cutplane_disk` | |
| `inner_radius_mm` | `float` | Required for `cutplane_annulus` | |
| `outer_radius_mm` | `float` | Required for `cutplane_annulus` | |
| `x_half_width_mm` | `float` | Required for `cutplane_rect` | |
| `z_half_width_mm` | `float` | Required for `cutplane_rect` | |
| `area_mm2` | `float` | **yes** unless `named_selection` | Computed from shape params |
| `axial_x_mm` | `float` | **yes** unless `named_selection` | Projection of center onto body axis |
| `parent_feature` | `str` | *optional* | Source hole/unroof in `.holes.json` |
| `source_type` | `enum{shaft, coil}` | *optional* | For hole_caps only |
| `selection_tag` | `str` | Required for `named_selection` | COMSOL named selection tag |
| `open_length_mm` | `float` | Required for `unroof_patch` | Axial extent of unroof opening |
| `sign_convention` | `str` | **yes** | Always `"positive_into_stent_lumen"` |

#### `HoleCap` (specialization of `MeasurementFeature` where `feature_class == "hole_cap"`)

Additional semantic fields:
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `source_type` | `enum{shaft, coil}` | **yes** | |
| `parent_feature` | `str` | **yes** | Must match a `hole_id` in `.holes.json` |
| `radius_mm` | `float` | **yes** | Must equal the hole radius from the parent |

#### `UnroofPatch` (specialization where `feature_class == "unroof_patch"`)

Additional semantic fields:
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `open_length_mm` | `float` | **yes** | Must be ≥ 0 and ≤ stent_length |
| `x_half_width_mm` | `float` | **yes** | |
| `z_half_width_mm` | `float` | **yes** | |

#### `CrossSection` (specialization where `feature_class == "cross_section"`)

Additional semantic fields:
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `metadata.section_role` | `str` | **yes** | One of `distal_lumen_partition`, `distal_annulus_partition` |
| `geometry_type` | One of `cutplane_disk` or `cutplane_annulus` | **yes** | |

#### `PressureReference` (specialization where `feature_class == "pressure_ref"`)

Additional semantic fields:
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `selection_tag` | `str` | **yes** | Must correspond to a COMSOL named selection |
| `metadata.selection_role` | `str` | **yes** | One of `baseline_inlet_reference`, `baseline_outlet_reference` |

#### `Zone`
| Field | Type | Notes |
|-------|------|-------|
| `name` | `enum{prox, mid, dist}` | |
| `axial_start_mm` | `float` | Left boundary (inclusive) |
| `axial_end_mm` | `float` | Right boundary (exclusive for internal boundaries) |
| `features` | `List[MeasurementFeature]` | All features assigned to this zone |

#### `FluxResult` (per-feature, one row in the long-form CSV)
| Field | Type | Required |
|-------|------|----------|
| `design_id` | `str` | **yes** |
| `feature_id` | `str` | **yes** |
| `feature_class` | `str` | **yes** |
| `zone` | `str` | **yes** |
| `area_mm2` | `float` | **yes** |
| `signed_flux_ml_min` | `float` | **yes** |
| `abs_flux_ml_min` | `float` | **yes** |
| `active` | `bool` | **yes** |
| `p_ramp` | `float or NA` | *optional* |
| `open_length_mm` | `float or NA` | For unroof patches |

#### `SummaryRecord` (per-design, one row in the summary CSV)

All 37+ fields currently defined in `flux_extraction.py::summarize_flux_outputs()` plus additions listed in §6 and §10.

### 2.2 Naming Convention Contract

All feature IDs must follow these patterns:

| Feature class | Pattern | Examples |
|---------------|---------|----------|
| `hole_cap` (shaft) | `cap_hole_shaft_{zone}_{NNN}` | `cap_hole_shaft_prox_003` |
| `hole_cap` (coil) | `cap_hole_coil_{zone}_{NNN}` | `cap_hole_coil_dist_001` |
| `unroof_patch` | `patch_unroof_{N}` | `patch_unroof_1` |
| `cross_section` (lumen) | `sec_distal_lumen` | |
| `cross_section` (annulus) | `sec_distal_annulus` | |
| `pressure_ref` (inlet) | `sec_inlet_ref` | |
| `pressure_ref` (outlet) | `sec_outlet_ref` | |

Where `{zone} ∈ {prox, mid, dist}` and `{NNN}` is a zero-padded three-digit index within (zone, type).

**Invariant:** `feature_id` values are unique within a design and stable across re-exports of the same design parameters.

---

## 3. Candidate Zoning Rules

The problem: given a hole at 3D position `p` with `axial_x_mm = p[0]`, assign it to one of `{prox, mid, dist}`.

### 3.1 Rule A: Global-axis projection with fixed-fraction boundaries

**Definition:**  
Let `L = stent_length`. Define:
- `prox`: `[0, L/3)`
- `mid`: `[L/3, 2L/3)`
- `dist`: `[2L/3, L]`

**Assumptions:** The stent is straight and aligned to `+X`. Zones are equal-length.

**Failure case:** The actual section lengths (`section_length_prox`, `section_length_dist`) are independent design variables, not fixed at `L/3`. For `section_length_prox = 20, stent_length = 300`, the true proximal section is only 6.7% of the stent, not 33%. A hole at `x = 25` in the mid section would be misclassified as proximal.

**Counterexample:** `stent_length=140, section_length_prox=24, section_length_dist=30`. Zone boundary for prox would be `x=46.7` by equal-thirds, but the actual prox section ends at `x=24`. A shaft hole at `x=30` (clearly in mid) would be misclassified as prox.

**Verdict:** **Unacceptable.** Does not respect the actual parameterization.

### 3.2 Rule B: Normalized axial coordinate using actual section boundaries

**Definition:**  
Let `L_p = section_length_prox`, `L_m = section_length_mid`, `L_d = section_length_dist`. Define:
- `prox`: `axial_x_mm ∈ [0, L_p)`
- `mid`: `axial_x_mm ∈ [L_p, L_p + L_m)`
- `dist`: `axial_x_mm ∈ [L_p + L_m, L]`

Boundary-case rule: if `|axial_x_mm - boundary| < ε` (say ε = 0.1 mm), assign to the zone whose center is closer.

**Assumptions:** Stent is straight with body axis on `+X`, body starts at `x = 0`. Section lengths are known at zone-assignment time.

**Failure case for automation:** Coil holes exist at `x < 0` (proximal coil) and `x > L` (distal coil), outside the body interval. Rule B assigns them to no zone.

**Fix:** Extend rule: features with `axial_x_mm < 0` are `prox`; features with `axial_x_mm > L` are `dist`.

**Counterexample (subtle):** A coil hole at `axial_x_mm = -5.25` on the proximal coil is geometrically "before" the proximal section. Rule B (extended) assigns it to `prox`, which is semantically correct because the proximal coil drains into the kidney-side reservoir.

**Verdict:** **Acceptable for straight stents with the extension.** This is essentially what the current implementation does at CAD generation time.

### 3.3 Rule C: Parent-region metadata from CAD generation

**Definition:**  
Zone is assigned at CAD time based on which section interval the hole was placed in:
- Shaft holes: the section (`prox`, `mid`, `dist`) that generated them
- Coil holes: `prox` if on the proximal coil, `dist` if on the distal coil
- Unroof patch: `dist` (always, by construction)
- Cross-sections and pressure refs: assigned explicitly by role

The assigned zone is stored in `*.meters.json` as the `zone` field and in `*.holes.json` as the `region` field.

**Assumptions:** The CAD generator is authoritative about which section each hole belongs to. The generator's section boundaries match the design parameters exactly.

**Failure case:** If a downstream consumer re-derives zones from coordinates and the generator's section boundaries differ from the consumer's assumed boundaries, disagreement occurs. This is a configuration error, not a logic error.

**Counterexample (benign):** After unroof-aware distal rebalance, a distal hole may be repositioned to `x = L_p + L_m + buffer`, very close to the mid/dist boundary. The generator still labels it `dist` because it was generated in the distal section, even though it's geometrically near the boundary. This is **correct behavior**—the hole was intended as a distal drainage hole.

**Counterexample (problematic):** None found in the current codebase. The generator's section boundaries are derived from the exact same `section_length_prox` and `section_length_dist` values, so there is no source of disagreement.

**Verdict:** **Best rule for this project.** It is deterministic, does not require geometric re-analysis, handles coil holes naturally, and is already implemented.

### 3.4 Rule D: Centerline arclength (for curved stents)

**Definition:**  
Parameterize the stent by arclength `s` along the centerline. Define zones by arclength fractions or by mapping the section-length parameters to arclength intervals.

**Assumptions:** A centerline exists and is well-defined. For the current straight-body + helical-coil design, the body centerline is trivially the `+X` axis.

**Failure case:** The coils are helical, so arclength along the coil ≠ axial projection. A coil hole at arclength `s = 15` mm along the coil may have `axial_x_mm = -5` mm.

**Verdict:** **Not needed for v1.** All current designs have straight bodies. Arclength is only relevant if the body itself becomes curved (e.g., S-shaped stents). The complexity is not justified now. If the body becomes curved in future versions, this rule should replace Rule B as the geometric fallback.

---

## 4. Recommended Zoning Rule

**Use Rule C (parent-region metadata) as the primary zone assignment.**

**Audit invariant (implemented as a QC check, not an override):**

For every `hole_cap` feature `f` with `f.zone = z`:

```
let [x_start_z, x_end_z] = zone_interval(z, section_length_prox, section_length_mid, section_length_dist, stent_length)
assert f.axial_x_mm ∈ [x_start_z - coil_extension_tolerance, x_end_z + coil_extension_tolerance]
```

where:
- `zone_interval("prox", ...) = [bbox_min_x, section_length_prox]`
- `zone_interval("mid", ...) = [section_length_prox, section_length_prox + section_length_mid]`
- `zone_interval("dist", ...) = [section_length_prox + section_length_mid, bbox_max_x]`
- `coil_extension_tolerance = max(pitch * turns, 10.0)` mm for coil holes, 0 for shaft holes

If a feature violates this invariant, it is a **warning** (not a rejection). The metadata label is still authoritative, but the warning should be logged and investigated.

---

## 5. Measurement-Feature Validity Criteria

### 5.1 HoleCap

**Necessary conditions (hard-fail if violated):**

| # | Condition | Rationale |
|---|-----------|-----------|
| H1 | `feature_class == "hole_cap"` | Type correctness |
| H2 | `geometry_type == "cutplane_disk"` | Only disks are valid hole caps |
| H3 | `center_mm` is a 3-vector of finite floats | Geometric well-definedness |
| H4 | `normal` is a 3-vector with `‖normal‖ ∈ [0.99, 1.01]` | Unit-length normal |
| H5 | `radius_mm > 0` and `radius_mm ≤ ID / 2` | Cap fits inside lumen |
| H6 | `area_mm2 > 0` and `|area_mm2 - π·radius_mm²| / area_mm2 < 0.01` | Area consistency |
| H7 | `parent_feature` matches a `hole_id` in `*.holes.json` | Traceability |
| H8 | The cap disk does not geometrically overlap any other cap disk in the same design (center-to-center distance > max(r₁, r₂) for non-identical caps) | Physical distinctness |

**Sufficient conditions (cap is usable if all hold):**

All of H1–H8, plus:

| # | Condition |
|---|-----------|
| H9 | `source_type ∈ {"shaft", "coil"}` |
| H10 | `zone ∈ {"prox", "mid", "dist"}` |
| H11 | `axial_x_mm == center_mm[0]` (within tolerance 0.01 mm) |

**Warning-but-usable conditions:**

| # | Condition | Action |
|---|-----------|--------|
| HW1 | `radius_mm < 0.1` mm | Warn: "tiny hole cap, may produce negligible flux" |
| HW2 | `source_type == "coil"` and cap_center_rule contains "currently uses" | Warn: "coil cap placement is provisional" |
| HW3 | Normal direction is not predominantly radial for shaft holes (i.e., `|normal · body_axis| > 0.5`) | Warn: "cap normal is not perpendicular to body axis" |

**Invalid conditions (hard-fail):**

| # | Condition |
|---|-----------|
| HX1 | `center_mm` is outside the design bounding box by more than `coil_extension_tolerance` |
| HX2 | `radius_mm ≤ 0` |
| HX3 | `normal` is the zero vector |

### 5.2 UnroofPatch

**Necessary conditions:**

| # | Condition | Rationale |
|---|-----------|-----------|
| U1 | `feature_class == "unroof_patch"` | |
| U2 | `geometry_type == "cutplane_rect"` | |
| U3 | `center_mm`, `normal` are valid 3-vectors | |
| U4 | `x_half_width_mm > 0`, `z_half_width_mm > 0` | |
| U5 | `open_length_mm > 0` | Zero-length unroof is meaningless |
| U6 | `open_length_mm ≤ stent_length` | Cannot exceed body length |
| U7 | The unroof patch axial extent `[center_mm[0] - x_half_width_mm, center_mm[0] + x_half_width_mm]` lies within the body interval `[0, stent_length]` or within one hole-radius of the boundary | Patch must correspond to a real opening |
| U8 | `area_mm2 > 0` and `|area_mm2 - 4 · x_half_width_mm · z_half_width_mm| / area_mm2 < 0.01` | Area consistency |

**When should an unroof be one feature vs. multiple?**

**Rule:** One `unroof_patch` per contiguous unroofed opening. If the design has two separate unroofed segments (not currently supported by the generator but possible in future), each gets its own `patch_unroof_N` feature.

**Condition for splitting:** Two openings are "separate" if they are separated by at least `2 · wall_thickness` of intact wall along the body axis.

**Current status:** The generator produces at most one unroof patch. This is correct for v1.

### 5.3 CrossSection

**Necessary conditions:**

| # | Condition | Rationale |
|---|-----------|-----------|
| C1 | `feature_class == "cross_section"` | |
| C2 | `geometry_type ∈ {"cutplane_disk", "cutplane_annulus"}` | |
| C3 | `normal` is parallel to the body axis (within 5° angular tolerance) | Cross-section must be transverse |
| C4 | For `cutplane_disk`: `radius_mm > 0` and `radius_mm ≤ r_inner + 0.1` (lumen section must fit inside inner wall) | |
| C5 | For `cutplane_annulus`: `0 < inner_radius_mm < outer_radius_mm` | |
| C6 | The `sec_distal_lumen` and `sec_distal_annulus` features must be at the same axial position | Partition consistency |
| C7 | For the lumen/annulus pair: the annulus `inner_radius_mm` must be ≥ the lumen `radius_mm` | No physical overlap (gap is acceptable—it represents the wall) |

**When does lumen/annulus partition break?**

The partition assumes that at the measurement cross-section plane, the flow domain separates cleanly into a "inside the stent" disk and an "outside the stent" annulus. This fails when:
- The cross-section plane is in the unroofed region (stent wall is missing on one side)
- The cross-section plane is at a hole location (hole creates a gap in the wall)
- The cross-section plane is in the coil region (coil geometry is not cylindrical)

**Rule:** The distal cross-section plane must be placed at an `axial_x_mm` value that satisfies:
1. `axial_x_mm > section_length_prox + section_length_mid` (in the distal section)
2. `axial_x_mm < stent_length - unroofed_length` (before the unroof opening)
3. No hole cap center is within `2 · hole_radius` axially of the cross-section plane

**Current implementation:** `sec_distal_lumen` is at `x = 139.0` for the 140 mm design. The unroof starts at `x = 140 - 13.26 = 126.74`. So the cross-section is at `x = 139.0`, which is **inside the unroofed region**. This is potentially incorrect if the unroof removes wall material at that axial position.

**Ambiguity identified:** The cross-section position at `x = 139.0` may be in the unroofed zone for designs with `unroofed_length > 1.0`. The current generator places it at `stent_length - 1.0` which is typically inside the unroof region. **This should be reviewed.** The safe rule is to place the cross-section at `stent_length - unroofed_length - max(2.0, 2 · hole_radius)`.

### 5.4 PressureReference

**Necessary conditions:**

| # | Condition | Rationale |
|---|-----------|-----------|
| P1 | `feature_class == "pressure_ref"` | |
| P2 | `geometry_type == "named_selection"` | |
| P3 | `selection_tag` is non-empty and matches a COMSOL named selection | |
| P4 | There is exactly one inlet reference and exactly one outlet reference per design | ΔP requires exactly two reference points |

**For ΔP to be meaningful:**
- The inlet and outlet reference surfaces must be at the physical inlet and outlet of the simulation domain (not at arbitrary internal planes)
- The surfaces must be large enough that surface-averaged pressure is representative
- The flow at the reference surfaces should be approximately unidirectional (no large recirculation zones at the reference plane)

**Current status:** Inlet and outlet are `named_selection` types pointing at the dumbbell reservoir caps. This is correct for the current domain geometry.

---

## 6. Formal Metric Definitions

All metrics assume the sign convention: **positive flux = into the stent lumen**.

Let:
- `F = {f₁, ..., fₙ}` be the set of all `hole_cap` features
- `U = {u₁, ..., uₖ}` be the set of all `unroof_patch` features (currently k ≤ 1)
- `q(f)` = signed flux through feature `f` (mL/min), positive = into lumen
- `|q|(f)` = absolute flux = `|q(f)|` (mL/min)
- `a(f)` = area of feature `f` (mm²)
- `ε` = active threshold (default `1e-6` mL/min)

### 6.1 Global Metrics

| Metric | Symbol | Definition | Unit |
|--------|--------|------------|------|
| Total outlet flow | `Q_out` | Surface integral of `(v · n)` over outlet, converted to mL/min | mL/min |
| Total inlet flow | `Q_in` | Surface integral of `(v · n)` over inlet, converted to mL/min (expected negative under sign convention) | mL/min |
| Inlet average pressure | `p_in` | Surface average of pressure on inlet reference | Pa |
| Outlet average pressure | `p_out` | Surface average of pressure on outlet reference | Pa |
| Pressure drop | `ΔP` | `p_in - p_out` | Pa |
| Conductance | `G` | `Q_out / ΔP` | mL/min/Pa |

**Precondition for `G`:** `|ΔP| > 1e-15`. If violated, `G = NaN`.

### 6.2 Pathway Partition Metrics

| Metric | Symbol | Definition | Unit |
|--------|--------|------------|------|
| Lumen outflow | `Q_lumen_out` | Signed flux through `sec_distal_lumen` | mL/min |
| Annulus outflow | `Q_annulus_out` | Signed flux through `sec_distal_annulus` | mL/min |
| Lumen fraction | `frac_lumen_out` | `Q_lumen_out / Q_out` | dimensionless |
| Annulus fraction | `frac_annulus_out` | `Q_annulus_out / Q_out` | dimensionless |

**Precondition for fractions:** `|Q_out| > 1e-15`. If violated, fractions = `NaN`.

**Note:** `frac_lumen_out + frac_annulus_out` does **not** necessarily equal 1.0 because:
1. The partition cross-section may not capture all flow (gap between lumen disk and annulus inner radius = wall thickness)
2. There may be unroof exchange downstream of the cross-section
3. Numerical integration errors

**Invariant (soft):** `|frac_lumen_out + frac_annulus_out - 1| < 0.05` should hold for well-resolved simulations with the cross-section upstream of the unroof. If violated, flag as QC warning.

### 6.3 Per-Hole Metrics

| Metric | Symbol | Definition |
|--------|--------|------------|
| Signed flux | `q(fᵢ)` | Signed surface integral through cap `fᵢ` |
| Absolute flux | `\|q\|(fᵢ)` | `\|q(fᵢ)\|` |
| Active flag | `active(fᵢ)` | `1 if \|q\|(fᵢ) > ε, else 0` |

### 6.4 Hole Summary Metrics

| Metric | Symbol | Definition |
|--------|--------|------------|
| Total signed hole flux | `Q_holes_net` | `Σᵢ q(fᵢ)` |
| Total absolute hole flux | `Q_holes_abs` | `Σᵢ \|q\|(fᵢ)` |
| Number of active holes | `n_active` | `Σᵢ active(fᵢ)` |

### 6.5 Zone-Level Hole Metrics

For each zone `z ∈ {prox, mid, dist}`:

| Metric | Symbol | Definition |
|--------|--------|------------|
| Zone absolute hole flux | `Q_z_hole_abs` | `Σ_{fᵢ : zone(fᵢ)=z} \|q\|(fᵢ)` |
| Zone fraction of total hole flux | `frac_z_hole_abs` | `Q_z_hole_abs / Q_holes_abs` |

**Precondition for fractions:** `Q_holes_abs > 1e-15`. If violated, fractions = `NaN`.

**Invariant (hard):** `frac_prox_hole_abs + frac_mid_hole_abs + frac_dist_hole_abs = 1.0` (within floating-point tolerance, say `|sum - 1| < 1e-10`), whenever all three are defined.

### 6.6 Hole Uniformity Metrics

Let `A = {fᵢ : active(fᵢ) = 1}` be the set of active holes, `n = |A|`.

#### 6.6.1 Coefficient of Variation (CV)

```
CV = σ(|q|(A)) / μ(|q|(A))
```

where `σ` is population standard deviation (`ddof=0`) and `μ` is mean.

**Precondition:** `n ≥ 2` and `μ > 0`. Otherwise `CV = NaN`.

**When meaningful:** CV captures relative spread. It is scale-invariant and interpretable as "fractional dispersion." Good for comparing designs with different total flows.

**When misleading:** CV can be very large when one hole dominates and others are near-zero. This is informative (high inequality) but can be confused with "noise" if the near-zero holes are just below the activity threshold. CV is also undefined for a single active hole, which is a valid design state.

#### 6.6.2 Gini Coefficient

```
Gini = (Σᵢ Σⱼ ||q|(fᵢ) - |q|(fⱼ)|) / (2n² · μ(|q|(A)))
```

**Precondition:** `n ≥ 2` and `μ > 0`.

**When meaningful:** Gini is bounded in `[0, 1]` (0 = perfect equality, 1 = maximal inequality). More robust to outliers than CV. Better for comparing hole distributions across designs with very different hole counts.

**When misleading:** Gini is insensitive to the distinction between "2 holes carrying 50/50" and "10 holes carrying 10/10/10/..." Both give Gini ≈ 0. If you care about the *number* of active pathways, Gini alone is insufficient.

**Implementation status:** Not yet implemented. Should be added.

#### 6.6.3 Entropy-Based Uniformity

Let `pᵢ = |q|(fᵢ) / Q_holes_abs` for active holes. Then:

```
H = -Σᵢ pᵢ log₂(pᵢ)
H_max = log₂(n)
H_norm = H / H_max   (normalized entropy, in [0, 1])
```

**Precondition:** `n ≥ 2` and `Q_holes_abs > 0`.

**When meaningful:** Entropy captures both the "number of effective pathways" and the "evenness." `H_norm = 1` means perfectly uniform. `H_norm → 0` means one hole dominates.

**When misleading:** Entropy is harder to interpret intuitively than CV or Gini. It is sensitive to very small flux values (a hole with `|q| = 1e-7` will have a very negative `p log p` contribution if `Q_holes_abs` is small).

**Recommendation:** Implement CV (already done) and Gini. Use CV as the primary uniformity metric for the surrogate. Add Gini and entropy as diagnostic outputs for analysis.

### 6.7 Unroof Metrics

| Metric | Symbol | Definition |
|--------|--------|------------|
| Signed unroof flux | `Q_unroof_net` | `Σⱼ q(uⱼ)` |
| Absolute unroof flux | `Q_unroof_abs` | `Σⱼ \|q\|(uⱼ)` |
| Unroof fraction of outlet | `frac_unroof_of_total` | `Q_unroof_abs / \|Q_out\|` |
| Unroof flux density | `ρ_unroof` | `Q_unroof_abs / Σⱼ open_length_mm(uⱼ)` |
| Unroof-vs-holes ratio | `R_uh` | `Q_unroof_abs / Q_holes_abs` |

**Preconditions:**
- `frac_unroof_of_total`: `|Q_out| > 1e-15`
- `ρ_unroof`: `Σ open_length_mm > 1e-15`
- `R_uh`: `Q_holes_abs > 1e-15`

**Ambiguity noted:** `frac_unroof_of_total` divides by `Q_out` (total outlet flow), not by total exchange flux. This means the fraction can exceed 1.0 if unroof absolute flux exceeds outlet flow (possible in recirculating flows). An alternative definition using `Q_exchange_total_abs = Q_holes_abs + Q_unroof_abs` as denominator would be bounded in `[0, 1]` by construction. Both should be computed; the `Q_out`-based version is comparable to the lumen/annulus fractions, while the exchange-based version is comparable to the zone fractions.

### 6.8 Combined Exchange Metric

| Metric | Symbol | Definition |
|--------|--------|------------|
| Total absolute exchange | `Q_exchange_total_abs` | `Q_holes_abs + Q_unroof_abs` |

### 6.9 Mass Balance

| Metric | Symbol | Definition |
|--------|--------|------------|
| Mass balance relative error | `mass_balance_relerr` | `\|Q_in + Q_out\| / max(\|Q_in\|, \|Q_out\|, ε)` |

Note: under the sign convention, `Q_in < 0` (flow enters domain) and `Q_out > 0` (flow exits domain). For perfect conservation, `Q_in + Q_out = 0`. The relative error should be < 0.01 (1%).

---

## 7. Invariants and Sanity Checks

### 7.1 Hard Invariants (must always hold; violation = bug)

| # | Invariant | Scope |
|---|-----------|-------|
| I1 | `∀ f: |q|(f) ≥ 0` | Per-feature |
| I2 | `∀ f: |q|(f) ≥ |q(f)|` | By definition of absolute value (holds with equality) |
| I3 | `Q_holes_abs ≥ |Q_holes_net|` | Triangle inequality on sums |
| I4 | `n_active ≥ 0` and `n_active ≤ |F|` | Counting |
| I5 | `∀ f: active(f) = 1 ⟹ |q|(f) > ε` | Activity definition |
| I6 | `∀ f: active(f) = 0 ⟹ |q|(f) ≤ ε` | Activity definition |
| I7 | `frac_prox_hole_abs + frac_mid_hole_abs + frac_dist_hole_abs ∈ [1 - δ, 1 + δ]` for `δ = 1e-10`, when all three are defined | Partition |
| I8 | `feature_id` values are unique within a design | Schema |
| I9 | `area_mm2 > 0` for all non-`named_selection` features | Physical |
| I10 | `|‖normal‖ - 1| < 0.01` for all features with normals | Unit-length |

### 7.2 Conditional Invariants (hold under stated assumptions)

| # | Invariant | Assumption |
|---|-----------|------------|
| IC1 | `ΔP > 0` | Pressure-driven flow with `p_in > p_out` |
| IC2 | `Q_out > 0` | Net positive outflow through outlet |
| IC3 | `Q_in < 0` | Net inflow through inlet (sign convention) |
| IC4 | `mass_balance_relerr < 0.01` | Well-converged incompressible simulation |
| IC5 | `G > 0` | Positive conductance (follows from IC1 + IC2) |
| IC6 | `frac_lumen_out ∈ [0, 1]` and `frac_annulus_out ∈ [0, 1]` | Cross-section upstream of all exchange, no recirculation |
| IC7 | `frac_unroof_of_total ∈ [0, 1]` | No dominant recirculation |

### 7.3 QC Heuristics (flag but do not reject)

| # | Check | Threshold | Interpretation |
|---|-------|-----------|----------------|
| QC1 | `n_active_holes == 0` when `|F| > 0` | — | All holes are dead; possible mesh/solver issue |
| QC2 | `max(|q|(f)) / min(|q|(f)) > 100` among active holes | — | Extreme non-uniformity; check mesh resolution |
| QC3 | `Q_exchange_total_abs / |Q_out| > 2.0` | — | Exchange flux far exceeds outlet; possible recirculation |
| QC4 | `Q_exchange_total_abs / |Q_out| < 0.01` and `|F| > 0` | — | Exchange is negligible; holes may not be resolving |
| QC5 | Any `|q(f)| > 0.5 · |Q_out|` for a single hole | — | Single hole dominates total drainage |
| QC6 | `|frac_lumen_out + frac_annulus_out - 1| > 0.05` | — | Pathway partition does not close |
| QC7 | `CV > 2.0` | — | Very high non-uniformity |

---

## 8. Edge Cases and Resolution Rules

### 8.1 Curved or Coiled Regions Where Axial Position Is Ambiguous

**Failure mode:** Coil holes have 3D positions far from the body axis (e.g., `y = 3.8, z = 5.0`). Their `axial_x_mm` is the projection onto the body axis, which may differ substantially from arclength along the coil.

**What a naive rule gets wrong:** Using `axial_x_mm` for spatial ordering places coil holes among shaft holes, but their physical flow path is through the helical lumen, not the straight shaft.

**Better rule:** Assign zone from parent metadata (Rule C). For plotting, use `axial_x_mm` as the x-coordinate but visually distinguish coil vs. shaft holes with different markers. Never interpolate between a coil hole and the nearest shaft hole on an "axial flux profile."

**Classification:** **Deterministic auto-resolve** via metadata.

### 8.2 Holes Near Zone Boundaries

**Failure mode:** A hole at `x = section_length_prox ± 0.05 mm` could be assigned to either prox or mid by a coordinate-based rule.

**What a naive rule gets wrong:** Floating-point rounding in `>=` vs `>` comparisons causes non-deterministic assignment.

**Better rule:** The generator places holes within section intervals with at least `BUFFER_MIN = 1.0 mm` clearance from section boundaries. Therefore, a correctly generated hole is always at least 1.0 mm from any boundary. If a hole is within 0.1 mm of a boundary, it indicates a generator bug, not a zone-assignment ambiguity.

**Classification:** **Deterministic auto-resolve** (buffer guarantees separation). If buffer is violated, **hard-fail** (generator validation error).

### 8.3 Flipped Normals

**Failure mode:** If a cap's normal points into the lumen instead of outward (or vice versa), the signed flux has the wrong sign.

**What a naive rule gets wrong:** Silently produces flux values with inverted sign, making "inflow" holes appear as "outflow" and vice versa.

**Better rule:** At COMSOL integration time, the normal orientation determines sign. The `*.meters.json` records the intended normal direction. The COMSOL method must use the recorded normal for the cut-plane orientation. Sign validation is done by checking that the majority of hole fluxes have the expected sign (positive = into lumen, for a pressure-driven system where fluid enters the lumen through holes). If more than 50% of holes have negative signed flux, flag a **QC warning** for potential global normal flip.

**Classification:** **Warning-but-continue** if a minority of holes show reversed sign (physically plausible for some holes). **Hard-fail** if all normals appear flipped (systematic error).

### 8.4 Tiny or Degenerate Holes

**Failure mode:** A hole with `radius_mm < 0.05` has area `< 0.008 mm²`. COMSOL mesh elements on such a small feature may not resolve the flow, producing noisy or zero flux values.

**What a naive rule gets wrong:** Includes the hole in uniformity metrics, pulling CV up without physical meaning.

**Better rule:** The `active` flag already handles this: holes with `|q| < ε` are excluded from uniformity calculations. Additionally, at CAD time, enforce `d_sh ≥ d_sh_min = 0.3 mm` (already in parameters.yaml). If a coil hole has effective radius below 0.05 mm due to geometry intersection issues, flag as **warning** and exclude from uniformity metrics but still report flux.

**Classification:** **Warning-but-continue** (report flux, exclude from uniformity if inactive).

### 8.5 Merged Openings

**Failure mode:** Two holes placed close together may have overlapping caps, creating a single merged opening.

**What a naive rule gets wrong:** Counts two features for what is physically one opening. Double-counts flux.

**Better rule:** At CAD generation time, enforce `GAP_MIN = 0.3 mm` between hole centers (already implemented). For caps, check that center-to-center distance > `max(r₁, r₂)`. The generator's hole-packing validation (`_validate_hole_packing`) should prevent this. If caps do overlap (e.g., due to coil geometry creating holes at similar axial positions from different turns), merge them into a single measurement feature with combined area, or flag as **hard-fail** during validation.

**Classification:** **Hard-fail** if caps geometrically overlap. The feasibility filter should prevent this.

### 8.6 Unroof Region Spanning Multiple Zones

**Failure mode:** An unroof with `open_length_mm = 25` starting at `x = 115` on a 140 mm stent would extend from `x = 115` to `x = 140`. If `section_length_dist = 30` (starting at `x = 110`), the unroof is entirely within `dist`. But if `section_length_dist = 20` (starting at `x = 120`), the unroof would extend from mid into dist.

**What a naive rule gets wrong:** Assigns the entire unroof patch to one zone, missing that it spans two.

**Better rule:** The current generator always places the unroof at the distal end of the stent. Its `zone` is always `"dist"`. If future designs allow mid-section unroofing, the unroof patch's zone assignment should be determined by where its center lies, with a **warning** if the patch axial extent crosses a zone boundary.

**Current implementation:** The `unroof_patch` zone is hardcoded to `"dist"`. This is correct for v1.

**Classification:** **Deterministic auto-resolve** for v1. **Warning-but-continue** if unroof center is in one zone but extent crosses into another (future designs).

### 8.7 Disagreement Between Geometry-Derived and Metadata-Derived Zone

**Failure mode:** A sidecar says `zone = "prox"` but coordinate analysis says the hole is in the mid-section interval.

**What a naive rule gets wrong:** Overrides the metadata, potentially misassigning a hole that was intentionally placed near a boundary.

**Better rule:** Trust the metadata label. Log a warning with: `"feature {feature_id}: metadata zone={z_meta}, coordinate zone={z_coord}, axial_x={x}. Using metadata zone."` Investigate if the discrepancy exceeds the buffer distance.

**Classification:** **Warning-but-continue.**

### 8.8 Geometrically Present Features That Should Not Count Physiologically

**Failure mode:** A coil hole that is entirely enclosed by the reservoir geometry (kidney or bladder) is geometrically present but physiologically irrelevant—it connects the coil lumen to a bulk fluid reservoir, not to the ureter annulus.

**What a naive rule gets wrong:** Includes the hole in side-hole metrics, inflating `Q_holes_abs` and distorting uniformity.

**Better rule:** Coil holes are kept in the per-feature table (for completeness) but can be excluded from shaft-hole uniformity metrics by filtering on `source_type == "shaft"`. The current `hole_flux.py::build_shaft_hole_flux_targets()` already does this by filtering `type == "shaft"`. However, `flux_extraction.py::summarize_flux_outputs()` includes **all** hole_caps (shaft and coil) in `Q_holes_abs` and zone summaries. This is a **design decision**, not a bug: coil holes do contribute to total exchange. But the uniformity CV should optionally be computed over shaft-only holes. **Recommend adding `shaft_hole_uniformity_cv` alongside the current `hole_uniformity_cv`.**

**Classification:** **Deterministic auto-resolve** by providing both all-hole and shaft-only metrics.

### 8.9 Caps Whose Center Is Reasonable But Mouth Orientation Is Wrong

**Failure mode:** A coil hole's cap normal is computed from the helix tangent, but the actual opening into the annular space may face a different direction due to the intersection of the cylindrical bore with the helical tube wall.

**What a naive rule gets wrong:** The cut-plane orientation misses the actual opening, capturing wall surface instead of lumen fluid.

**Better rule:** For shaft holes, the normal is radially outward from the body axis, which is geometrically correct. For coil holes, the provisional rule uses the coil-center/axis, which is approximate. The `cap_center_rule` metadata field documents this. The long-term fix is dedicated coil-mouth reconstruction. For now, **accept the provisional rule** and validate by checking that coil-hole fluxes are physically reasonable (same order of magnitude as nearby shaft holes, or at least non-zero and finite).

**Classification:** **Warning-but-continue** with explicit metadata annotation.

### 8.10 Distal Pathway Sections Where Lumen/Annulus Separation Is Not Clean

**Failure mode:** In the unroofed region, the stent wall is removed on one side. A cross-section plane here does not cleanly separate "lumen" from "annulus"—the lumen disk and annulus annulus have a gap where the wall was, allowing fluid to cross freely.

**What a naive rule gets wrong:** Reports `frac_lumen_out` and `frac_annulus_out` values that don't sum to 1 and are not interpretable as "through the stent" vs. "around the stent."

**Better rule:** Place the lumen/annulus partition cross-section **upstream** of the unroof region:
```
x_partition = max(section_length_prox + section_length_mid + buffer, stent_length - unroofed_length - 2 * max(buffer, hole_radius))
```

If `unroofed_length` is so large that no valid partition position exists within the distal section, set `frac_lumen_out = NaN` and `frac_annulus_out = NaN` and flag a **warning**.

**Classification:** **Warning-but-continue** if partition can't be cleanly placed; **deterministic auto-resolve** if partition is placed upstream of unroof.

---

## 9. Feasibility-Rule Specification

### 9.1 Current State

The current `FeasibilityFilter` (in `feasibility.py`) delegates entirely to `StentParameters.__post_init__()`, catching `ValueError` exceptions. This provides:
1. `ID ≥ ID_MIN` (0.6 mm)
2. `section_length_mid ≥ 10 mm`
3. Per-section hole packing: `n_holes × pitch_min ≤ L_use`

### 9.2 Missing Constraints

The following necessary constraints are **not currently enforced:**

#### F1: Unroof/hole collision avoidance (partially implemented)

The generator's `_compute_and_finalize_holes()` handles distal-hole rebalance when `unroofed_length > 0`, but the **feasibility filter** does not reject designs where no distal holes survive the rebalance. This may or may not be desirable (a design with zero distal shaft holes but a large unroof may be valid).

**Rule:** If `unroofed_length > 0` and the unroofed region covers the entire distal section (`unroofed_length ≥ section_length_dist`), reject unless `n_dist == 0`.

**Formal constraint:**
```
unroofed_length ≤ section_length_dist - 2 × max(BUFFER_MIN, hole_radius)
OR n_dist == 0
OR (unroofed_length > 0 AND legal_end > dist_start)  [auto-rebalance succeeds]
```

#### F2: Section length positivity

The generator checks `section_length_mid ≥ 10`, but does not check:
- `section_length_prox ≥ 2 × BUFFER_MIN` (so at least one hole can fit)
- `section_length_dist ≥ 2 × BUFFER_MIN`
- `section_length_prox + section_length_dist ≤ stent_length - 10` (mid section minimum)

These are implicitly enforced by the YAML ranges (`[20, 60]` for prox/dist, `[100, 300]` for total length) but should be explicit hard constraints.

**Formal constraints:**
```
section_length_prox ≥ 2 × max(BUFFER_MIN, hole_radius)  [if n_prox > 0]
section_length_dist ≥ 2 × max(BUFFER_MIN, hole_radius)  [if n_dist > 0]
stent_length - section_length_prox - section_length_dist ≥ 10.0
```

#### F3: Minimum wall thickness for manufacturing

Referenced in `parameter_schema.md` as TBD. Should be:
```
wall_thickness = r_t × OD ≥ wall_min
```

where `wall_min` is a manufacturing constraint (e.g., 0.1 mm for polymers, 0.05 mm for metals). This is **not currently enforced.**

#### F4: Maximum hole-to-wall ratio

Also TBD in `parameter_schema.md`:
```
d_sh ≤ k × wall_thickness
```

for some structural factor `k` (e.g., `k = 5`). This prevents tissue prolapse through oversized holes. **Not currently enforced.**

#### F5: Cross-section placement feasibility

If the distal cross-section must be upstream of the unroof:
```
stent_length - unroofed_length - section_length_prox - section_length_mid > 2 × max(BUFFER_MIN, hole_radius)
```

This ensures there is a valid axial position for the lumen/annulus partition plane within the distal section but outside the unroofed region.

**If violated:** The design is feasible as a flow device but the lumen/annulus partition metric becomes undefined. This should be a **warning**, not a rejection.

#### F6: Coil-hole cap validity (no overlap with body)

Coil holes must not overlap with the body tube geometry:
```
∀ coil_hole_center c: ‖c_yz‖ > r_outer + hole_radius
OR the coil hole is outside the body axial interval [0, stent_length]
```

where `c_yz = (c[1], c[2])` is the radial displacement from the body axis.

**Current status:** The coil helix has `R = 6.0 mm` and the body `r_outer ≤ OD/2 ≤ 0.333×8/2 = 1.332 mm`, so `R ≫ r_outer`. This constraint is satisfied by a large margin for all current designs. **No action needed for v1**, but should be checked if coil geometry becomes a design variable.

### 9.3 Formal Feasible Set

Let `θ = (stent_french, stent_length, r_t, r_sh, r_end, n_prox, n_mid, n_dist, section_length_prox, section_length_dist, unroofed_length)` be the sampled parameter vector.

Derived quantities:
```
OD = 0.333 × stent_french
wall = r_t × OD
ID = OD - 2 × wall
d_sh = min(r_sh × ID, ID - CAP_MARGIN)
hole_radius = d_sh / 2
buffer = max(BUFFER_MIN, hole_radius)
pitch_min = d_sh + GAP_MIN
L_mid = stent_length - section_length_prox - section_length_dist
```

**Necessary constraints for geometric validity:**

| # | Constraint | Current enforcement |
|---|-----------|---------------------|
| C1 | `ID ≥ ID_MIN` (0.6 mm) | ✅ `StentParameters` |
| C2 | `L_mid ≥ 10.0` mm | ✅ `StentParameters` |
| C3 | `n_prox × pitch_min ≤ section_length_prox - 2 × buffer` (or `n_prox = 0`) | ✅ `StentParameters` |
| C4 | `n_mid × pitch_min ≤ L_mid - 2 × buffer` (or `n_mid = 0`) | ✅ `StentParameters` |
| C5 | `n_dist × pitch_min ≤ section_length_dist - 2 × buffer` (or `n_dist = 0`) | ✅ `StentParameters` |
| C6 | `section_length_prox ≥ 2 × buffer` if `n_prox > 0` | ⚠️ Implicitly via C3 |
| C7 | `section_length_dist ≥ 2 × buffer` if `n_dist > 0` | ⚠️ Implicitly via C5 |
| C8 | `unroofed_length ≤ section_length_dist` | ❌ Not enforced |
| C9 | `unroofed_length = 0 OR legal_dist_end > legal_dist_start OR n_dist = 0` | ⚠️ Partially via rebalance |
| C10 | `wall ≥ wall_min` (TBD) | ❌ Not enforced |
| C11 | `d_sh ≤ k × wall` (TBD) | ❌ Not enforced |

**Sufficient condition for a valid design:** C1–C9 all hold. The design can be generated, exported, and imported into COMSOL.

**Sufficient condition for all metrics to be computable:** C1–C9, plus `unroofed_length < section_length_dist - 2 × buffer` (ensures distal partition plane can be placed).

### 9.4 Recommended Feasibility Filter Implementation

```python
class FeasibilityResult(Enum):
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    REJECTED = "rejected"

def check_feasibility(θ) -> Tuple[FeasibilityResult, List[str], List[str]]:
    """
    Returns (result, rejection_reasons, warnings).
    """
    rejections = []
    warnings = []
    
    # Derive
    OD = 0.333 * θ.stent_french
    wall = θ.r_t * OD
    ID = OD - 2 * wall
    d_sh = min(θ.r_sh * ID, ID - CAP_MARGIN)
    hole_radius = d_sh / 2
    buffer = max(BUFFER_MIN, hole_radius)
    pitch_min = d_sh + GAP_MIN
    L_mid = θ.stent_length - θ.section_length_prox - θ.section_length_dist
    
    # C1
    if ID < ID_MIN:
        rejections.append(f"ID={ID:.3f} < ID_MIN={ID_MIN}")
    
    # C2
    if L_mid < 10.0:
        rejections.append(f"L_mid={L_mid:.1f} < 10.0")
    
    # C3–C5
    for name, n, L_sec in [("prox", θ.n_prox, θ.section_length_prox),
                            ("mid", θ.n_mid, L_mid),
                            ("dist", θ.n_dist, θ.section_length_dist)]:
        if n > 0:
            L_use = L_sec - 2 * buffer
            if n * pitch_min > L_use:
                rejections.append(f"hole_packing_{name}: need {n * pitch_min:.1f} > avail {L_use:.1f}")
    
    # C8
    if θ.unroofed_length > θ.section_length_dist:
        rejections.append(f"unroofed_length={θ.unroofed_length:.1f} > section_length_dist={θ.section_length_dist:.1f}")
    
    # C9 (check that distal rebalance has room if n_dist > 0 and unroofed_length > 0)
    if θ.unroofed_length > 0 and θ.n_dist > 0:
        dist_start = θ.section_length_prox + L_mid + buffer
        unroof_start = θ.stent_length - θ.unroofed_length
        legal_end = min(θ.stent_length - buffer, unroof_start - buffer)
        if legal_end <= dist_start:
            warnings.append(f"no_room_for_dist_holes_after_unroof_rebalance")
    
    # C10 (when wall_min is defined)
    # if wall < WALL_MIN:
    #     rejections.append(f"wall={wall:.3f} < WALL_MIN={WALL_MIN}")
    
    # Warning: cross-section placement
    if θ.unroofed_length > 0:
        cs_space = θ.section_length_dist - θ.unroofed_length
        if cs_space < 2 * buffer:
            warnings.append("insufficient_space_for_distal_partition_plane")
    
    if rejections:
        return (FeasibilityResult.REJECTED, rejections, warnings)
    elif warnings:
        return (FeasibilityResult.VALID_WITH_WARNINGS, [], warnings)
    else:
        return (FeasibilityResult.VALID, [], [])
```

---

## 10. Better Derived Metrics If Warranted

### 10.1 Problem with Current Zone-Summed Outputs

The current pipeline outputs `prox_hole_abs_flux`, `mid_hole_abs_flux`, `dist_hole_abs_flux`. These have three weaknesses:

1. **They lose per-hole information.** A design with 3 prox holes at {0.1, 0.1, 0.1} mL/min looks identical to one with 3 prox holes at {0.0, 0.0, 0.3} mL/min.

2. **Zone boundaries are arbitrary.** If the design changes `section_length_prox` from 30 to 25, holes shift zones, making cross-design comparisons unreliable.

3. **They cannot represent "where along the stent does drainage concentrate?"** This is arguably the most clinically relevant question.

### 10.2 Proposed Additional Metrics

#### 10.2.1 Flux-Weighted Axial Centroid

```
x̄_flux = Σᵢ (axial_x_mm(fᵢ) × |q|(fᵢ)) / Q_holes_abs
```

**Precondition:** `Q_holes_abs > 1e-15`.

**Interpretation:** The "center of drainage activity" along the stent axis. If `x̄_flux` is near the proximal end, most exchange happens proximally. If near the distal end, distally.

**Normalized version:**
```
x̄_norm = x̄_flux / stent_length ∈ [0, 1]
```

This is comparable across designs of different lengths.

#### 10.2.2 Flux-Weighted Axial Spread

```
σ_flux = sqrt(Σᵢ ((axial_x_mm(fᵢ) - x̄_flux)² × |q|(fᵢ)) / Q_holes_abs)
```

**Interpretation:** How spread out the drainage activity is along the stent. Low `σ_flux` means drainage is concentrated at one location. High `σ_flux` means it is distributed along the length.

**Normalized version:**
```
σ_norm = σ_flux / stent_length
```

#### 10.2.3 Effective Number of Active Pathways

```
n_eff = exp(H) = exp(-Σᵢ pᵢ log pᵢ)
```

where `pᵢ = |q|(fᵢ) / Q_holes_abs` and the sum is over active holes.

**Interpretation:** The entropy-based "effective number of equal-contribution holes." A design with 10 holes where only 2 carry real flow has `n_eff ≈ 2`.

#### 10.2.4 Competition Ratios

```
R_prox_vs_dist = Q_prox_hole_abs / max(Q_dist_hole_abs, ε)
R_holes_vs_unroof = Q_holes_abs / max(Q_unroof_abs, ε)
```

**Interpretation:** Direct comparisons of drainage pathways. `R_prox_vs_dist > 1` means proximal drainage dominates.

#### 10.2.5 Dimensionless Conductance Groups

```
G* = G × (μ / (ID³))    [dimensionless]
```

where `μ` is fluid viscosity (0.001 Pa·s for the current model).

**Interpretation:** Collapses scale effects, making conductance comparable across French sizes.

### 10.3 Recommendation

**Add to the primary output table:**
- `x̄_norm` (flux centroid, normalized)
- `σ_norm` (flux spread, normalized)
- `n_eff` (effective number of pathways)
- `R_holes_vs_unroof` (already implemented as `unroof_vs_holes_ratio`)

**Keep as-is (backward compatibility):**
- `prox_hole_abs_flux_ml_min` / `mid_hole_abs_flux_ml_min` / `dist_hole_abs_flux_ml_min`
- `frac_prox_hole_abs` / `frac_mid_hole_abs` / `frac_dist_hole_abs`

**Reason:** The centroid/spread pair is strictly more informative than the zone-fraction triple for optimization because it captures localization without depending on arbitrary zone boundaries. However, zone-level metrics should remain for interpretability.

---

## 11. Minimal Implementation Contract for Coding Agents

### 11.1 CAD Generator Contract

**Inputs:** `StentParameters` dataclass.

**Outputs:**
1. `{design_id}.step` — STEP geometry in canonical frame (+X axis, body start at x=0)
2. `{design_id}.holes.json` — Hole sidecar (schema version `hole_metadata_sidecar_v2`)
3. `{design_id}.meters.json` — Measurement surface sidecar (schema version `measurement_surface_sidecar_v1`)

**Post-conditions:**
- Every hole in `.holes.json` has a corresponding `hole_cap` in `.meters.json`
- Every `hole_cap` in `.meters.json` has `parent_feature` matching a `hole_id` in `.holes.json`
- Feature IDs follow the naming convention in §2.2
- All coordinates are in the canonical export frame
- `validate_measurement_surface_metadata()` passes without error
- If `unroofed_length > 0`, there is exactly one `unroof_patch` feature
- There is exactly one `sec_distal_lumen`, one `sec_distal_annulus`, one `sec_inlet_ref`, one `sec_outlet_ref`
- `feature_groups` in the sidecar are consistent with the `features` list

### 11.2 COMSOL Extraction Contract

**Inputs:**
- `{design_id}.meters.json`
- Solution dataset (from a converged COMSOL solve)

**Outputs:**
1. `{design_id}_flux_scalars.csv` containing at minimum:
   - `Q_out_ml_min`, `Q_in_ml_min`
   - `p_in_avg_Pa`, `p_out_avg_Pa`
   - `Q_lumen_out_ml_min`, `Q_annulus_out_ml_min`
   - `max_vel_m_s`, `max_p_Pa`, `min_p_Pa`
   - `mesh_ndof`, `solver_converged_flag`, `solver_message`

2. `{design_id}_flux_features.csv` containing one row per measurement feature:
   - `feature_id`, `feature_class`, `zone`
   - `signed_flux_ml_min`, `abs_flux_ml_min`
   - `area_mm2`
   - `open_length_mm` (for unroof patches)

**Post-conditions:**
- Every `feature_id` in the features CSV matches a `feature_id` in `.meters.json`
- `abs_flux_ml_min ≥ 0` for all rows
- `abs_flux_ml_min ≥ |signed_flux_ml_min|` for all rows (within tolerance 1e-12)
- No duplicate `feature_id` values per `p_ramp` step

### 11.3 Python Postprocessor Contract

**Inputs:**
- `{design_id}_flux_scalars.csv`
- `{design_id}_flux_features.csv`

**Output:**
- One-row summary DataFrame containing all metrics defined in §6, keyed by `design_id` and optionally `p_ramp`.

**Post-conditions:**
- All hard invariants (§7.1) hold
- All conditional invariants (§7.2) hold whenever their preconditions are met
- QC heuristics (§7.3) are evaluated and stored in a `qc_warnings` field
- Empty-feature cases produce `NaN` for dependent metrics, never division-by-zero errors
- The summary includes per-hole columns `Q_hole_{parent_feature}_ml_min`, `absQ_hole_{parent_feature}_ml_min`, `hole_active_{parent_feature}` for every hole_cap feature

### 11.4 Feasibility Filter Contract

**Input:** A DataFrame row or `StentParameters`-compatible dictionary.

**Output:** `(FeasibilityResult, List[rejection_reasons], List[warnings])`

**Post-conditions:**
- A `REJECTED` result guarantees the design cannot be generated by `StentParameters.__post_init__()` without error
- A `VALID` result guarantees `StentParameters` can be instantiated and `.generate()` will produce valid STEP + sidecar
- All rejection reasons are deterministic (same input → same output)

---

## 12. Open Uncertainties

| # | Uncertainty | Impact | Suggested Resolution |
|---|-------------|--------|---------------------|
| O1 | **Coil-hole cap orientation is provisional.** The current rule uses the helix tangent, which may not align with the actual opening geometry. | Per-hole flux for coil holes may be inaccurate. | Implement dedicated coil-mouth reconstruction or validate against a reference geometry with known coil-hole flux. |
| O2 | **Distal cross-section placement may be inside the unroofed region** for designs with large `unroofed_length`. | `frac_lumen_out` and `frac_annulus_out` become uninterpretable. | Move the cross-section upstream of the unroof region (§8.10). Requires generator change. |
| O3 | **`wall_min` and `d_sh / wall` constraints are TBD.** | The feasibility filter cannot reject structurally invalid designs. | Determine manufacturing constraints and add to feasibility filter. |
| O4 | **The annulus outer radius for `sec_distal_annulus` is hardcoded to 4.0 mm** (the dumbbell template ureter radius). | If the domain template changes, this value becomes wrong. | Derive from the simulation contract or template metadata. |
| O5 | **The Gini metric is documented but not implemented.** | Incomplete uniformity characterization. | Implement `hole_uniformity_gini` in `flux_extraction.py`. |
| O6 | **The legacy grouped path (`q_sh_prox/mid/dist` via `result_parser.py`) and the per-feature path (`flux_extraction.py`) are not yet converged.** | Two separate code paths that must agree. | Deprecate the legacy grouped path once per-feature extraction is validated end-to-end. |
| O7 | **No formal sign-validation test for the COMSOL extraction method.** | A global normal flip in the cut-plane construction would silently invert all signs. | Add a smoke test: run a known-good design, verify that the majority of hole fluxes are positive (into lumen) and that `Q_out > 0`. |
| O8 | **The normalized entropy metric and flux centroid/spread metrics are not yet implemented.** | Current outputs are weaker than they could be for optimization. | Implement in `flux_extraction.py::summarize_flux_outputs()`. |
| O9 | **Sensitivity of mesh resolution on per-hole flux accuracy is uncharacterized.** | Reported per-hole fluxes may be mesh-dependent. | Run a mesh convergence study on one design, comparing per-hole flux at different mesh densities. |
| O10 | **Current sign convention for `Q_in` is not explicitly documented in the COMSOL method.** The expectation `Q_in < 0` is in `expectations.py` but not enforced in the extraction method. | Sign mismatch between COMSOL output and Python postprocessor. | Add explicit sign check in the Java extraction method. |
