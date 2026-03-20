# COMSOL Output + Automated Extraction Framework for the Pediatric Stent Project

## 1) Decision rule

This framework separates outputs into:
- **Tier 1 = required for the surrogate / optimization CSV**
- **Tier 2 = required QC / interpretation diagnostics**
- **Tier 3 = optional research-only extras**

The goal is to keep the surrogate table compact, but keep enough structure that side-hole, unroofed-region, and bypass behavior can still be interpreted.

---

## 2) Conclusive output list

## Tier 1 — REQUIRED MODEL OUTPUTS (one row per design / phase / condition)

### Global drainage
1. **Q_out_ml_min**  
   Total outlet volumetric flow rate.

2. **deltaP_Pa**  
   Pressure drop between the designated inlet and outlet reference sections.

3. **conductance_ml_min_per_Pa**  
   `Q_out_ml_min / deltaP_Pa`

### Pathway partitioning
4. **Q_lumen_out_ml_min**  
   Flow leaving through the distal in-stent lumen cross-section.

5. **Q_annulus_out_ml_min**  
   Flow leaving through the distal extra-stent / annular cross-section.

6. **frac_lumen_out**  
   `Q_lumen_out / Q_out`

7. **frac_annulus_out**  
   `Q_annulus_out / Q_out`

### Side-hole exchange (per aperture)
8. **Q_hole_<id>_ml_min** for every hole  
   Signed flux through each side-hole measurement cap.

9. **absQ_hole_<id>_ml_min** for every hole  
   Absolute flux magnitude through each side-hole cap.

10. **hole_active_<id>**  
   Binary active flag, e.g. `absQ_hole_<id> > epsilon`.

### Side-hole summary metrics
11. **Q_holes_net_ml_min**  
   Sum of signed side-hole fluxes.

12. **Q_holes_abs_ml_min**  
   Sum of absolute side-hole fluxes.

13. **hole_uniformity_cv**  
   Coefficient of variation of `absQ_hole_<id>` over active holes.

14. **hole_uniformity_gini**  
   Optional inequality metric for hole activation.

15. **n_active_holes**  
   Number of active holes.

16. **prox_hole_abs_flux_ml_min**  
   Sum of absolute side-hole flux in proximal zone.

17. **mid_hole_abs_flux_ml_min**  
   Sum of absolute side-hole flux in middle zone.

18. **dist_hole_abs_flux_ml_min**  
   Sum of absolute side-hole flux in distal zone.

### Unroofed-region exchange
19. **Q_unroof_net_ml_min**  
   Signed flux through the unroofed-region measurement patch.

20. **Q_unroof_abs_ml_min**  
   Absolute flux magnitude through the unroofed-region patch.

21. **frac_unroof_of_total**  
   `Q_unroof_abs / Q_out`

22. **unroof_flux_density_ml_min_per_mm**  
   `Q_unroof_abs / unroof_open_length_mm`

23. **unroof_vs_holes_ratio**  
   `Q_unroof_abs / max(Q_holes_abs, eps)`

### Pressure references
24. **p_in_avg_Pa**  
   Surface-averaged pressure on the inlet reference section.

25. **p_out_avg_Pa**  
   Surface-averaged pressure on the outlet reference section.

These 25 outputs are the recommended minimum set for the main structured CSV.

---

## Tier 2 — REQUIRED QC / INTERPRETATION DIAGNOSTICS

26. **Q_in_ml_min**  
   Inlet volumetric flow.

27. **mass_balance_relerr**  
   Relative imbalance, e.g. `|Q_in - Q_out| / max(|Q_in|, eps)` for incompressible baseline.

28. **mesh_ndof**  
   Number of degrees of freedom.

29. **solver_converged_flag**  
   1 if converged, else 0.

30. **solver_message**  
   Short status string / failure code.

31. **max_vel_m_s**  
   Global max velocity magnitude.

32. **max_p_Pa**  
   Global max pressure.

33. **min_p_Pa**  
   Global min pressure.

34. **Q_exchange_total_abs_ml_min**  
   `Q_holes_abs + Q_unroof_abs`

35. **frac_mid_hole_abs**  
   `mid_hole_abs_flux / Q_holes_abs`

36. **frac_prox_hole_abs**

37. **frac_dist_hole_abs**

These are not all optimization objectives, but they are necessary to interpret the runs and gate bad simulations.

---

## Tier 3 — OPTIONAL RESEARCH OUTPUTS

38. **WSS_max_on_hole_rims_Pa**  
39. **WSS_mean_on_unroof_rim_Pa**  
40. **local_recirc_index_near_<feature>**  
41. **axial_center_of_hole_activity_mm**  
42. **axial_center_of_unroof_activity_mm**  
43. **phase_id / constriction_snapshot_id** for Tier A quasi-steady snapshots  
44. **flow_reversal_flag_<feature>**  

These are useful for plots and papers, but should not be the first outputs the surrogate depends on.

---

## 3) What not to use as primary outputs

Do **not** make these first-class optimization targets yet:
- absolute WSS thresholds
- local recirculation magnitude as a clinical claim
- pressure-drop-as-physiology once forced tissue/peristaltic surrogates are added

Keep them as comparative diagnostics only.

---

## 4) Core measurement principle

## Side-hole and unroofed flux must be measured on dedicated measurement surfaces

Do **not** try to define per-hole flux by integrating on the literal hole wall.
A wall is tangential/no-slip boundary information; it is **not** the exchange surface you want.

Instead:
- every side hole gets a **cap surface** spanning the opening
- the unroofed segment gets a **patch surface** spanning that opening
- lumen/annulus partition gets **distal cross-sections**
- inlet/outlet pressure uses **reference sections**, not arbitrary boundary nodes

This is the single most important modeling choice in the framework.

---

## 5) Geometry assets required from CAD

The CAD generator should output, per design:

1. **Main fluid geometry**
2. **Measurement surfaces package** containing:
   - `cap_hole_<id>` for each side hole
   - `patch_unroof_1` for the unroofed opening
   - `sec_inlet_ref`
   - `sec_outlet_ref`
   - `sec_distal_lumen`
   - `sec_distal_annulus`
3. **Sidecar metadata JSON** containing, for each measurement surface:
   - stable ID
   - class (`hole_cap`, `unroof_patch`, `cross_section`, `pressure_ref`)
   - zone (`prox`, `mid`, `dist`)
   - centroid
   - normal
   - area
   - design-local parent feature name

Recommended filenames:
- `<design_id>.fluid.step`
- `<design_id>.meters.step`
- `<design_id>.meters.json`

---

## 6) Robust COMSOL extraction strategy

## Preferred strategy: import measurement surfaces as named geometry features

### Why this is the right way
It avoids trying to rediscover holes from boundary indices after import.
Boundary/entity numbers are fragile across geometry changes.

### Implementation concept
- Import fluid geometry.
- Import measurement-surface geometry.
- Ensure the measurement surfaces become selectable entities in the model.
- Create named selections for each measurement surface, or for each group of surfaces.
- Evaluate flux/pressure on those selections using numerical result features.

If a geometry pipeline cannot yet create these measurement surfaces, use coordinate-based selections only as a temporary fallback.

---

## 7) Fallback strategy if measurement surfaces are not yet in CAD

### Temporary fallback A — coordinate-based named selections
Use named selections built from COMSOL `Ball`, `Box`, or `Cylinder` selections driven by the sidecar coordinates.

This is acceptable for:
- grouping proximal/mid/distal hole neighborhoods
- coarse region diagnostics
- pressure reference sections if they are planar and easy to localize

It is **not** the best long-term solution for per-hole exchange.

### Temporary fallback B — cut-plane datasets
For simple planar cross-sections, define `CutPlane` datasets and integrate normal velocity over a logical mask.
This is good for:
- inlet/outlet reference planes
- lumen vs annulus partition planes

It is **not** good for arbitrary curved or oblique hole openings unless you want a lot of brittle setup logic.

---

## 8) Numerical features to create in COMSOL

For a stationary laminar-flow model with solution dataset `dset1`, create:

### A. Global evaluations
- `gev_qout`
- `gev_deltap`
- `gev_conductance`
- `gev_qin`
- `gev_massbal`
- `gev_maxvel`
- `gev_maxp`
- `gev_minp`

### B. Surface integrations
- `int_hole_<id>` for each hole cap
- `int_unroof_1`
- `int_dist_lumen`
- `int_dist_annulus`
- `int_inlet_ref_flux`
- `int_outlet_ref_flux`

### C. Surface averages
- `avg_inlet_p`
- `avg_outlet_p`

### D. Optional maxima / minima / averages on selections
- `max_wss_hole_<id>`
- `avg_wss_unroof`

---

## 9) Recommended expressions

Assume a 3D incompressible Laminar Flow interface with dependent variables `u, v, w, p`.

### Volumetric flux through a measurement surface
Use the signed normal velocity flux:

`u*nx + v*ny + w*nz`

Integrated with `IntSurface`, this gives volumetric flow in `m^3/s`.
Convert to `mL/min` by multiplying by `6e7`.

Recommended stored expression:

`6e7*(u*nx + v*ny + w*nz)`

### Absolute exchange magnitude through a measurement surface

`6e7*abs(u*nx + v*ny + w*nz)`

### Average pressure on a reference section

`p`

with a `Surface Average` numerical feature.

### Pressure drop

`p_in_avg - p_out_avg`

### Conductance

`Q_out_ml_min / deltaP_Pa`

---

## 10) Sign convention

Pick one convention and freeze it in the template.

Recommended:
- positive side-hole / unroof flux = flow **into the stent lumen**
- negative = flow **out of the lumen**

Because COMSOL uses the surface normal orientation, you should:
1. encode intended normals in the CAD measurement surfaces when possible
2. validate sign on one canonical template design
3. store both signed and absolute fluxes in CSV

That last point prevents downstream ambiguity.

---

## 11) Automation architecture

## Layer 1 — CAD / metadata
Python CAD generator creates:
- fluid STEP
- measurement STEP
- metadata JSON

## Layer 2 — COMSOL model method
A model method should:
1. load the design-specific geometry
2. rebuild/import geometry
3. rebuild selections from metadata
4. run mesh
5. run solve
6. run numerical evaluations
7. write one structured CSV row (plus optional long-form per-hole CSV)

## Layer 3 — outer driver
A shell / Python driver calls COMSOL in batch mode with method-call inputs:
- `design_id`
- geometry file paths
- metadata file path
- output CSV path

---

## 12) Suggested file outputs

## A. Main row-wise surrogate table
One row per design/condition.

Suggested file:
- `design_outputs.csv`

Columns begin with:
- `design_id`
- `run_id`
- `condition_id`
- `phase_id`
- all Tier 1 outputs
- selected Tier 2 outputs
- status fields

## B. Per-feature long table
One row per measurement feature.

Suggested file:
- `feature_flux_long.csv`

Columns:
- `design_id`
- `run_id`
- `condition_id`
- `feature_id`
- `feature_class`
- `zone`
- `area_mm2`
- `signed_flux_ml_min`
- `abs_flux_ml_min`
- `avg_pressure_Pa` (optional)

This table is what you use for the cool per-hole graphs.

## C. QC log
Suggested file:
- `run_qc.csv`

Columns:
- `design_id`
- `mesh_ok`
- `solve_ok`
- `mass_balance_relerr`
- `solver_message`
- `ndof`
- `wallclock_s`

---

## 13) COMSOL API pattern to use

The documented COMSOL API pattern is:
- create numerical features under `model.result().numerical()`
- point them to named selections or datasets
- retrieve values with `getReal()`
- optionally collect them in tables and export tables to CSV

Use **named selections** for geometry entities and **IntSurface / EvalGlobal / Surface Average** result features.
For batch sweeps, group evaluations in an **Evaluation Group** when useful.

---

## 14) Minimal model-method pseudocode

```java
// Inputs:
// design_id, fluid_step_path, meters_step_path, meters_json_path, out_csv_path, out_feature_csv_path

void RunDesignExtraction(String designId,
                         String fluidStepPath,
                         String metersStepPath,
                         String metersJsonPath,
                         String outCsvPath,
                         String outFeatureCsvPath) {

    // 1. Clear prior design-specific geometry/selections/results if needed
    // 2. Import geometry
    // 3. Import measurement surfaces
    // 4. Read metadata JSON
    // 5. Create / refresh named selections
    // 6. Mesh + solve
    // 7. Create numerical result features if missing
    // 8. For each measurement surface selection:
    //      IntSurface signed flux
    //      IntSurface abs flux
    // 9. Evaluate inlet/outlet average pressure
    // 10. Evaluate Q_out, lumen/annulus partition, QC metrics
    // 11. Aggregate zone metrics and uniformity metrics
    // 12. Append one row to design_outputs.csv
    // 13. Append per-feature rows to feature_flux_long.csv
}
```

---

## 15) What should be automated inside COMSOL vs outside COMSOL

## Inside COMSOL
- importing geometry
- rebuilding named selections
- mesh/solve
- numerical evaluation
- table/CSV export

## Outside COMSOL
- design generation
- metadata generation
- campaign bookkeeping
- failure retries
- surrogate training
- plotting and downstream statistics

This split keeps COMSOL focused on solving and postprocessing, not orchestration.

---

## 16) Exact recommendation for your current project

### Keep as primary optimization outputs now
- `Q_out_ml_min`
- `deltaP_Pa`
- `hole_uniformity_cv` or `hole_uniformity_gini`
- `Q_unroof_abs_ml_min` or `frac_unroof_of_total`
- `frac_lumen_out` / `frac_annulus_out`

### Keep as required diagnostics
- `mass_balance_relerr`
- `Q_in_ml_min`
- `solver_converged_flag`
- `mesh_ndof`
- `n_active_holes`

### Keep as optional extras
- WSS
- local recirculation
- local maxima near features

---

## 17) First implementation order

1. Add CAD-side measurement surfaces for all side holes.
2. Add one unroofed-region patch surface.
3. Add distal lumen / distal annulus partition sections.
4. Add inlet / outlet reference sections.
5. Build COMSOL named-selection-from-metadata method.
6. Build numerical-feature extraction method.
7. Export `design_outputs.csv` and `feature_flux_long.csv`.
8. Only after that, add Tier A snapshot / phase handling.

---

## 18) Non-negotiables

- Do not rely on manual boundary numbers.
- Do not define per-hole flux from wall boundaries.
- Do not let the surrogate depend first on fragile local WSS metrics.
- Always export both signed and absolute exchange flux.
- Always export a long-form per-feature table in addition to the one-row design table.

