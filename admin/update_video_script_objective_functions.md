# Update Video Script: Practical COMSOL Walkthrough

**[Video Intro]**
Welcome to this progress update. Today, we are looking at a major structural shift in how we handle the stent design pipeline. The overarching goal of our work is to optimize stent designs to maximize effective drainage while minimizing adverse effects. To do that reliably, we need an airtight connection between the CAD geometries we generate and the computational fluid dynamics (CFD) results we derive from them.

I want to use this update to formalize the project in the way I am actually thinking about it now. We are moving away from treating this as a loose "CAD-in, COMSOL-out" pipeline. Instead, we are formalizing the workflow into a strict, mathematically verified sequence of mappings on a controlled stent state-space. Every CAD parameter sampled, every feature realized, and every metric extracted is now rigorously governed by a measurement contract. This ensures our optimization objective functions are built on scientifically interpretable, physically consistent data.

Let's jump straight into COMSOL and look at how this is implemented.

---

## 1. The Design State & The Manifests

**[Action: Open `batch_0000.csv` side-by-side with COMSOL]**

The cleanest starting point is the design state itself. In our baseline campaign, we sample 11 parameters—French size, length, hole counts, etc. But the pipeline doesn't treat those raw parameters as the final geometry. It treats them as proposals.

We explicitly track the **realized design state**. Our manifests log both the requested parameters and the actual physical outcomes. For example, if unroofing logic suppresses a few nominal side-holes during CAD construction, our state-space accurately reflects the built stent—it doesn't pretend those holes still exist. This bridges the gap between geometry requests and physical reality.

---

## 2. The Formal Measurement Contract

**[Action: Show the `design_0000.meters.json` sidecar on screen]**

The next huge change is how we measure flow. We aren't measuring fluid exchange indiscriminately on arbitrary wall boundaries or by manually clicking faces in the COMSOL UI. We use a dedicated measurement sidecar, this `*.meters.json` file. 

**[Action: Highlight the feature classes in the JSON (`hole_cap`, `unroof_patch`, etc.)]**

This metadata file tells COMSOL exactly where and how to measure fluxes using stable cut-planes for every hole, unroof patch, and distal section. The extraction surfaces are generated from the very same geometry frame that built the STEP file.

**[Action: Show COMSOL Model Tree -> Highlight `CP_flux_*` and `DV_flux_*` nodes]**

Here’s what that looks like in the solver. These derived values aren't abstract Python inventions—they are explicit, named cut planes inside the COMSOL environment. By formalizing this measurement operator, we guarantee that our objective functions are scientifically interpretable transport patterns, not just presentation fluff. 

---

## 3. Objective Metrics & State Compression

**[Action: Show `<design_id>_flux_features.csv` and `<design_id>_flux_scalars.csv` side-by-side]**

Once COMSOL extracts these per-feature fluxes, we compress that data into a robust one-row summary, seen here in the scalars CSV. We track:
- **Throughput & Resistance**: Core metrics like pressure drop and outlet flow.
- **Exchange Magnitudes**: Both net and absolute fluid exchange moving through the side-holes and unroofed sections.
- **Exchange Number (Ex)**: A dimensionless ratio separating pure throughput from heavy sidewall exchange activity.
- **Spatial Localization**: Normalized flux centroids and interquartile spans, giving us a continuous physical descriptor of *where* flow is trading across the boundaries.

**[Action: Point out `deltaP_Pa`, `Q_out_ml_min`, `exchange_number`]**

This is why this measurement contract matters so much for later clinical translation. If a clinician asks where a specific stent exchanges fluid, we don't just point to an abstract scalar. We show them the normalized spatial distribution of absolute hole exchange derived from verifiable geometric cut-planes. 

---

## 4. The Formal Optimization Layers

Instead of collapsing everything into a single loss function and blindly feeding it to an optimizer, our system is divided into strict layers:

1. **Geometric Feasibility**: We immediately drop designs that violate physical CAD constraints.
2. **Physics consistency**: We run the raw CFD outputs through strict, mathematically verified Quality Control gates (using the Lean 4 theorem prover) to guarantee mass balance and physical invariants. If COMSOL hallucinates or diverges, the state gets dropped.
3. **Optimized Surrogates**: Only strictly valid, verified states make it to our Bayesian Optimization surrogate, which operates on transformed and stabilized targets to handle the complex trade-offs between pressure, throughput, and fluid exchange.

In short, rather than sending naive physics outputs to an optimizer, we actively filter the state-space through a formal mathematical proof layer. This ensures that when our acquisition algorithms tell us to sample a particular design next, they rely on a rigorously sound interpretation of fluid mechanics.

---

## 5. Current Status & Next Steps

**[Action: Briefly show `docs/baseline_validation_ladder.md` and the Tier A diagram (`docs/images/peristalsis_figure_pack/fig16_tierA_middle_cylinder_load.png`)]**

What we’ve got fully implemented right now is the metadata-first baseline screening chain for steady-state flow. We have manifest-driven campaign batches, the COMSOL extraction scripts running, the sidecars driving measurements, and the formal verifications successfully gating the data for the optimizer. 

The next step is extending this robust state-space. Since the baseline transport metrics are locked down, we’re now positioned to systematically add the more complex physics—peristaltic Tier A loads, cough cases, and stochastic anatomical variations—without rebuilding the pipeline from scratch.

---

## Manual COMSOL Warm-Start Checklist (COMSOL 6.1)

This is the first manual warm-start test path, assuming:

- `design_0000` already exists as a solved cold anchor
- multi-`p_ramp` exports already work
- the goal is one manual warm-start validation before any batch automation

### Exact `p_ramp` schedules

- `cold`: `0.1, 0.5, 0.75, 0.9, 0.95, 0.9625, 0.975, 0.9875, 0.995, 1.0`
- `warm90`: `0.9, 0.95, 0.9625, 0.975, 0.9875, 0.995, 1.0`
- `warm75`: `0.75, 0.9, 0.95, 0.9625, 0.975, 0.9875, 0.995, 1.0`

If the anchor run for `design_0000` used the full cold schedule above, then the stored solution-step mapping is:

- step `1` -> `0.1`
- step `2` -> `0.5`
- step `3` -> `0.75`
- step `4` -> `0.9`
- step `5` -> `0.95`
- step `6` -> `0.9625`
- step `7` -> `0.975`
- step `8` -> `0.9875`
- step `9` -> `0.995`
- step `10` -> `1.0`

### Exact UI path for initialization from the anchor solution

In COMSOL 6.1, go to:

- `Model Builder`
- `Study 1`
- `Solver Configurations`
- `Solution 1`
- `Stationary Solver 1`
- `Dependent Variables 1`

Then in `Settings` for `Dependent Variables 1`:

- find `Values of Dependent Variables`
- set `Initial values of variables solved for` = `User controlled`
- set `Method` = `Solution`

### How to choose anchor checkpoint `0.9` or `0.75`

After setting `Method = Solution`:

- choose the solved anchor solution as the source, usually `Study 1 / Solution 1`
- choose the stored solution number that corresponds to the anchor checkpoint

For the full cold `design_0000` anchor:

- use solution step `4` for anchor checkpoint `0.9`
- use solution step `3` for anchor checkpoint `0.75`

That gives the first two manual warm-start tests:

- `warm90` test = initialize from `design_0000`, solution step `4`
- `warm75` test = initialize from `design_0000`, solution step `3`

### How to keep the anchor solution available

Safest manual workflow:

- open the solved `design_0000` anchor `.mph`
- immediately do `File -> Save As` to a new warm-test file
- do not click `Clear All Solutions`
- do not reset the solver sequence
- make the new-design geometry/input edits only in that copied file

That way:

- the original `design_0000` file remains the preserved anchor
- the copied file carries the anchor solution data needed for manual initialization

### Expected CSV outputs

For the manual warm-start test, the main expected outputs are:

- `<design_id>_flux_scalars.csv`
- `<design_id>_flux_features.csv`

If the shaft/coil per-hole build methods are also run, expect:

- `<design_id>_shaft_hole_flux.csv`
- `<design_id>_coil_hole_flux.csv`

### What counts as success

Success means:

- COMSOL accepts `Method = Solution` without error
- the run starts from the chosen warm point, not from `0.1`
- the full warm schedule completes through `1.0`
- the expected CSV files are written
- the exported rows cover every `p_ramp` value in the chosen warm schedule
- the results are still physically sane: inlet pressure above outlet pressure, correct flow sign, and acceptable mass balance

### What counts as failure

Failure means:

- COMSOL cannot reference the anchor solution
- the solver fails immediately at the first warm step
- the run stalls before reaching `1.0`
- the CSV outputs are missing or only partially written
- the only way to finish is to manually back down and edit the schedule mid-run

### Recommended first manual order

The safest first manual sequence is:

1. try `warm75` from `design_0000` solution step `3`
2. if that works, try `warm90` from `design_0000` solution step `4`
