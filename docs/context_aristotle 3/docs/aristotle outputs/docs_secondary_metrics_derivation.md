# Secondary Metrics Derivation — Beyond Q_out and ΔP

## Summary of existing metrics (from repo inspection)

The following metrics are **already implemented or specified** in the codebase and are therefore out of scope for this document. References to source files are given for traceability.

### Primary / Tier-1 outputs (implemented in `src/comsol/flux_extraction.py::summarize_flux_outputs`)

| Metric | Key in code | Notes |
|--------|-------------|-------|
| Total outlet flow | `Q_out_ml_min` | Scalar CSV |
| Pressure drop | `deltaP_Pa` | `p_in_avg_Pa - p_out_avg_Pa` |
| Conductance | `conductance_ml_min_per_Pa` | `Q_out / deltaP` |
| Lumen/annulus partition fractions | `frac_lumen_out`, `frac_annulus_out` | |
| Per-hole signed & absolute flux | `Q_hole_<id>_ml_min`, `absQ_hole_<id>_ml_min` | Per-feature |
| Per-hole active flag | `hole_active_<id>` | Binary, threshold `1e-6 mL/min` |
| Net & absolute hole flux | `Q_holes_net_ml_min`, `Q_holes_abs_ml_min` | |
| Zone absolute flux triplet | `prox_hole_abs_flux_ml_min`, `mid_…`, `dist_…` | |
| Zone fraction triplet | `frac_prox_hole_abs`, `frac_mid_…`, `frac_dist_…` | |
| Hole uniformity CV | `hole_uniformity_cv` | `std/mean` over active holes |
| Active hole count | `n_active_holes` | |
| Unroof net & abs flux | `Q_unroof_net_ml_min`, `Q_unroof_abs_ml_min` | |
| Unroof fraction of total | `frac_unroof_of_total` | |
| Unroof flux density | `unroof_flux_density_ml_min_per_mm` | |
| Unroof-to-holes ratio | `unroof_vs_holes_ratio` | |
| Total exchange flux | `Q_exchange_total_abs_ml_min` | holes + unroof |
| Mass balance error | `mass_balance_relerr` | |

### Mentioned in `metrics_catalog.md` or `comsol_output_framework.md` but **not yet computed**

| Metric | Status | Notes |
|--------|--------|-------|
| `hole_uniformity_gini` | Listed as "optional inequality metric" in framework doc; **not implemented** | |
| `CV_Qsh` (zone-level CV) | Listed in metrics_catalog; **not identical** to `hole_uniformity_cv` (which is per-hole) | Ambiguity: see §3 |
| WSS_avg, WSS_max, OSI, RT_avg, Energy_Loss | Listed as Tier 2/3; **not implemented**, and explicitly deferred | |
| `axial_center_of_hole_activity_mm` | Listed as Tier 3 item 41 in framework doc; **not implemented** | This is a flux centroid concept |
| `flow_reversal_flag_<feature>` | Listed as Tier 3 item 44; **not implemented** | |

### GP surrogate setup (from `src/surrogate/gp_model.py`, `training.py`, `optimizer.py`)

- Model: `SingleTaskGP` with Matérn 5/2 + ARD, manual [0,1] input normalization, manual y-standardization.
- Multi-output is handled by a **single** `SingleTaskGP` with `outcome_dim > 1` — i.e., all outputs are modeled as a single multi-output GP (independent-output assumption via standard BoTorch).
- Optimizer uses `ScalarizedPosteriorTransform` with hand-set weights (`q_out: 1.0, delta_p: -0.001`).
- **Current GP targets** (inferred from the optimizer weights and output_variables in `parameters.yaml`): `Q_out`, `deltaP`, and likely `CV_Qsh`, plus the zone triplet. The `parameters.yaml` lists `Q_sh_prox`, `Q_sh_mid`, `Q_sh_dist`, `CV_Qsh` alongside `delta_P` and `Q_total`.

### Metrics already present that I will **not re-derive**

- CV (coefficient of variation)
- Gini (mentioned but not implemented — I will treat it as "specified" and not re-propose it; however I will note its relationship to new proposals)
- Entropy (mentioned in the user prompt as present — although I found no implementation, I treat it as specified)
- Flux centroid (listed as Tier 3 item 41, `axial_center_of_hole_activity_mm`)
- Flux spread (mentioned by user as present)

**Ambiguity alert**: The codebase has two distinct CV notions — `hole_uniformity_cv` (per-hole, over active holes) and `CV_Qsh` (per-zone, over the prox/mid/dist triplet). These are not interchangeable. `CV_Qsh` is a 3-sample CV and is inherently noisy; `hole_uniformity_cv` is more stable when there are many holes. Both are present in the spec. I treat both as existing.

---

## Notation conventions used below

| Symbol | Meaning |
|--------|---------|
| $N$ | Total number of holes (all types, all zones) |
| $N_a$ | Number of active holes ($\|q_i\| > \varepsilon$) |
| $q_i$ | Signed flux through hole $i$ (mL/min); positive = into lumen |
| $a_i = \|q_i\|$ | Absolute flux through hole $i$ |
| $x_i$ | Axial position of hole $i$ (mm along stent body axis) |
| $L$ | Stent body length (mm) |
| $Q_\text{out}$ | Total outlet flow (mL/min) |
| $\Delta P$ | Pressure drop (Pa) |
| $Q_\text{holes}^{\text{abs}} = \sum_i a_i$ | Total absolute hole exchange |
| $Q_\text{unroof}^{\text{abs}}$ | Total absolute unroof exchange |
| $Q_\text{exch}} = Q_\text{holes}^{\text{abs}} + Q_\text{unroof}^{\text{abs}}$ | Total absolute exchange |
| $\bar{a} = Q_\text{holes}^{\text{abs}} / N_a$ | Mean active-hole absolute flux |
| $\hat{x} = \sum_i a_i x_i / Q_\text{holes}^{\text{abs}}$ | Flux-weighted axial centroid (already specified as Tier 3) |
| Zone subscripts: $P$, $M$, $D$ | Proximal, mid, distal |

All formulas below reference quantities already extractable from `summarize_flux_outputs` or the per-feature long table.

---

## 1. Dimensionless exchange descriptors

### 1.1 Exchange Number (Stanton-like)

$$\mathrm{Ex} = \frac{Q_\text{exch}}{Q_\text{out}}$$

**Formula in pipeline terms**: `(Q_holes_abs_ml_min + Q_unroof_abs_ml_min) / Q_out_ml_min`

**Physical meaning**: Ratio of total wall-exchange flux to throughput flux. $\mathrm{Ex} = 0$ means a sealed pipe (no side exchange). $\mathrm{Ex} \gg 1$ means the stent wall recirculates far more fluid than it drains — indicating large bidirectional exchange. Analogous to the Stanton number in convective heat transfer (exchange rate / advective transport rate), but for mass rather than energy.

**Regime discrimination**:
- $\mathrm{Ex} < 0.1$: exchange-starved; side holes barely participate.
- $0.1 < \mathrm{Ex} < 1$: moderate exchange; side holes contribute meaningfully but throughput dominates.
- $\mathrm{Ex} > 1$: exchange-dominated; significant recirculation or multi-pass flow through the wall.

**Degenerate case**: When $Q_\text{out} \to 0$, $\mathrm{Ex}$ diverges. Convention: set $\mathrm{Ex} = \texttt{NaN}$ when $|Q_\text{out}| < \varepsilon$. This is physically meaningful — zero throughput with nonzero exchange is a stagnation/recirculation mode that should be flagged, not silently absorbed.

**Mesh robustness**: Yes — both numerator and denominator are integrals over well-defined surfaces; ratio cancels systematic mesh-convergence bias to first order.

**Clinical interpretability**: Only with context. "The stent exchanges 40% of its throughput through side holes" is communicable; the raw number is not.

**Use**: Diagnostic feature and potential optimization objective (e.g., maximize $\mathrm{Ex}$ subject to $\Delta P$ constraint).

**Correlation with existing metrics**: Partially correlated with `frac_unroof_of_total` and `Q_holes_abs`, but Ex unifies both exchange pathways into a single dimensionless number. Strictly more informative than either alone because it normalizes by throughput.

**Length-scale invariance**: Yes — both numerator and denominator scale with flow rate; insensitive to stent length rescaling at fixed Reynolds number.

---

### 1.2 Hole-Only Exchange Number

$$\mathrm{Ex}_h = \frac{Q_\text{holes}^{\text{abs}}}{Q_\text{out}}$$

**Formula**: `Q_holes_abs_ml_min / Q_out_ml_min`

**Physical meaning**: Like $\mathrm{Ex}$, but excluding the unroof contribution. Useful for comparing designs with and without an unroof patch on a level playing field.

**Degenerate case**: Same as $\mathrm{Ex}$; $\texttt{NaN}$ when $Q_\text{out} \approx 0$.

**Mesh robustness**: Yes.

**Clinical interpretability**: Only with context.

**Use**: Diagnostic. Essential for isolating the side-hole contribution from the unroof contribution in the presence of varying unroof lengths.

**Only meaningful when**: at least one hole is present ($N \geq 1$). For zero-hole designs, $\mathrm{Ex}_h = 0$ exactly — well-defined but trivial.

---

### 1.3 Normalized Conductance (Dimensionless Permeability)

$$G^* = \frac{G \cdot \mu \cdot L}{A_{\text{lumen}}}$$

where $G = Q_\text{out}/\Delta P$ is the dimensional conductance (already computed), $\mu$ is dynamic viscosity (Pa·s, a fixed simulation parameter = 0.001), $L$ is stent body length (mm, from sidecar), and $A_\text{lumen} = \pi (ID/2)^2$ is the lumen cross-sectional area (from sidecar).

**Formula**: `conductance_ml_min_per_Pa * (mu * L) / A_lumen`, with appropriate unit conversion (conductance is mL/min/Pa; need to convert to m³/s/Pa = m³·s⁻¹·Pa⁻¹).

Concretely, in SI:
$$G^* = \frac{Q_\text{out} [\text{m}^3/\text{s}]}{\Delta P [\text{Pa}]} \cdot \frac{\mu [\text{Pa·s}] \cdot L [\text{m}]}{A_\text{lumen} [\text{m}^2]}$$

This is dimensionless and equivalent to an inverse friction factor scaled by geometry.

**Physical meaning**: Measures how permeable the stent is relative to what a plain tube of the same bore and length would offer. $G^* = 1$ corresponds roughly to Hagen-Poiseuille conductance. Values above 1 indicate that side holes or the unroof are adding parallel flow paths; values below 1 are physically unlikely for an open tube.

**Degenerate case**: When $\Delta P = 0$, conductance is undefined; propagate $\texttt{NaN}$.

**Mesh robustness**: Conditional — conductance is mesh-sensitive at coarse meshes, but the ratio with geometric quantities cancels some discretization error.

**Clinical interpretability**: Yes — "this stent conducts 1.3× the flow a plain tube of the same bore would" is meaningful.

**Use**: Both optimization objective and diagnostic. Directly captures the engineering question "do the holes help?"

**Correlation**: Monotonically related to conductance, but adds normalization that makes values comparable across different stent diameters and lengths — strictly more informative for cross-design comparison.

**Length-scale invariance**: By construction, $G^*$ is invariant to proportional rescaling of $L$, $ID$, and flow conditions (at fixed Re).

---

### 1.4 Net Exchange Direction Index

$$\mathrm{NDI} = \frac{Q_\text{holes}^{\text{net}}}{Q_\text{holes}^{\text{abs}}}$$

**Formula**: `Q_holes_net_ml_min / Q_holes_abs_ml_min`

**Physical meaning**: Fraction of hole exchange that is net inward ($\mathrm{NDI} > 0$) vs net outward ($\mathrm{NDI} < 0$). $\mathrm{NDI} = +1$: all holes have inward flow. $\mathrm{NDI} = -1$: all holes have outward flow. $\mathrm{NDI} = 0$: perfectly balanced bidirectional exchange.

**Range**: $[-1, +1]$.

**Degenerate case**: When $Q_\text{holes}^{\text{abs}} = 0$ (no active holes), $\mathrm{NDI} = \texttt{NaN}$.

**Mesh robustness**: Yes — ratio of integrals.

**Clinical interpretability**: Yes — "are the holes draining or leaking?"

**Use**: Diagnostic feature. Potentially an optimization constraint (e.g., require $\mathrm{NDI} > 0$ to ensure net drainage through holes).

**Correlation**: Uncorrelated with CV, Gini, or any magnitude metric — it captures directional balance, an entirely independent degree of freedom.

**Requires**: $N_a \geq 1$.

---

### 1.5 Zone Flux Partition Vector (Dimensionless)

Already partially present as `frac_prox_hole_abs`, etc. But the existing implementation normalizes by `Q_holes_abs`. I note this here only to define a **generalized partition** that includes the unroof:

$$\vec{\pi} = \left(\frac{Q_P^{\text{abs}}}{Q_\text{exch}},\; \frac{Q_M^{\text{abs}}}{Q_\text{exch}},\; \frac{Q_D^{\text{abs}}}{Q_\text{exch}},\; \frac{Q_\text{unroof}^{\text{abs}}}{Q_\text{exch}}\right)$$

This 4-vector sums to 1 and gives a complete dimensionless exchange budget. It extends the existing 3-fraction to include unroof. Not a new "metric" per se, but a useful normalization for downstream descriptors.

---

## 2. Spatial localization metrics

All metrics in this section are defined over the active holes ($a_i > \varepsilon$) using their absolute fluxes and axial positions. The flux centroid $\hat{x}$ and a concept of "spread" are mentioned by the user as already present; I do not re-derive those. I focus on higher-order spatial statistics.

### 2.1 Flux Interquartile Span (IQS)

**Definition**: Construct the cumulative distribution function of absolute flux along the axis:

$$F(x) = \frac{\sum_{i: x_i \leq x} a_i}{Q_\text{holes}^{\text{abs}}}$$

Let $x_{25}$ and $x_{75}$ be the axial positions where $F$ first exceeds 0.25 and 0.75 respectively (linearly interpolated between hole positions if needed). Then:

$$\mathrm{IQS} = \frac{x_{75} - x_{25}}{L}$$

**Physical meaning**: The fraction of the stent length over which the middle 50% of the hole exchange occurs. $\mathrm{IQS} \to 0$ means exchange is concentrated at essentially one axial location. $\mathrm{IQS} \to 1$ means exchange is spread over the full stent.

**Degenerate cases**:
- $N_a = 0$: $\mathrm{IQS} = \texttt{NaN}$.
- $N_a = 1$: $\mathrm{IQS} = 0$ (all flux at one point).
- All flux in one zone: $\mathrm{IQS}$ is the zone length fraction.

**Perturbation stability**: Continuous in hole positions and flux magnitudes. Stable under small perturbations.

**Mesh robustness**: Yes — depends only on integral quantities per hole.

**Clinical interpretability**: Yes — "exchange is concentrated in the proximal 20% of the stent" is directly communicable.

**Use**: Diagnostic and optimization. A surgeon may want $\mathrm{IQS}$ above some threshold to ensure distributed drainage.

**Correlation with existing**: Distinct from CV/Gini (which measure flux magnitude inequality, not spatial spread). Related to but more robust than flux spread (variance-based spread is sensitive to outlier holes at extreme positions; IQS is not).

**Length-scale invariance**: Yes, by division by $L$.

---

### 2.2 Axial Flux Skewness

$$\gamma_1 = \frac{\sum_i a_i \left(\frac{x_i - \hat{x}}{\sigma_x}\right)^3}{Q_\text{holes}^{\text{abs}}}$$

where $\sigma_x = \sqrt{\sum_i a_i (x_i - \hat{x})^2 / Q_\text{holes}^{\text{abs}}}$ is the flux-weighted axial standard deviation (the "flux spread" already specified).

**Physical meaning**: Asymmetry of the flux distribution along the axis. $\gamma_1 > 0$: flux is skewed distally (long tail toward distal end). $\gamma_1 < 0$: skewed proximally. $\gamma_1 = 0$: symmetric about the centroid.

**Degenerate cases**:
- $N_a \leq 1$: $\sigma_x = 0$, so $\gamma_1 = \texttt{NaN}$.
- $N_a = 2$: $\gamma_1$ is well-defined but trivially determined by flux ratio.
- $\sigma_x = 0$ (all holes at same $x$): $\gamma_1 = \texttt{NaN}$.

**Perturbation stability**: Continuous but third-moment statistics are inherently more sensitive than second-moment ones. With $N_a < 5$, treat with caution.

**Mesh robustness**: Yes — depends only on per-hole integrals and positions.

**Clinical interpretability**: Only with context — "the flux is biased toward the proximal end."

**Use**: Diagnostic. Flags designs where exchange is unexpectedly lopsided.

**Correlation**: Orthogonal to CV, Gini (those are scale-free magnitude descriptors; this is a spatial shape descriptor). Independent of centroid and spread — it is the third standardized moment.

---

### 2.3 Axial Flux Kurtosis (Excess)

$$\gamma_2 = \frac{\sum_i a_i \left(\frac{x_i - \hat{x}}{\sigma_x}\right)^4}{Q_\text{holes}^{\text{abs}}} - 3$$

**Physical meaning**: Peakedness of the flux distribution. $\gamma_2 > 0$ (leptokurtic): flux is concentrated in a narrow band with heavy tails. $\gamma_2 < 0$ (platykurtic): flux is spread uniformly without heavy tails.

**Degenerate cases**: Same as skewness; requires $N_a \geq 3$ and $\sigma_x > 0$.

**Perturbation stability**: Fourth-moment statistics are the least stable. Use only when $N_a \geq 6$.

**Mesh robustness**: Yes.

**Clinical interpretability**: No — this is a mathematical shape descriptor.

**Use**: Diagnostic only. May help distinguish "two-cluster" distributions (high kurtosis) from "spread-out" ones.

**Correlation**: Independent of centroid, spread, and skewness by construction.

---

### 2.4 Cumulative Axial Flux Profile — Kolmogorov–Smirnov Departure from Uniform

$$D_\text{KS} = \sup_x \left| F(x) - \frac{x - x_{\min}}{x_{\max} - x_{\min}} \right|$$

where $F(x)$ is the empirical flux-weighted CDF defined in §2.1, and the reference is the uniform distribution over the hole span $[x_{\min}, x_{\max}]$.

**Physical meaning**: Maximum deviation of the actual flux distribution from perfectly uniform exchange along the stent. $D_\text{KS} = 0$: perfectly uniform. $D_\text{KS} = 1$: all flux at one end.

**Degenerate cases**:
- $N_a \leq 1$: $D_\text{KS} = \texttt{NaN}$ (can't define a span).
- All holes at same $x$: $D_\text{KS} = \texttt{NaN}$.

**Formula in pipeline terms**: Sort holes by $x_i$, compute the cumulative weighted fraction, compare to the uniform ramp between the most proximal and most distal active hole.

**Perturbation stability**: Yes — supremum of a piecewise-linear function is Lipschitz in hole positions and fluxes.

**Mesh robustness**: Yes.

**Clinical interpretability**: Only with context — "the drainage departs from uniform by 35%."

**Use**: Diagnostic. Combines spatial and magnitude information into one number. Alternative to IQS when a single departure statistic is preferred.

**Correlation**: Partially correlated with IQS and CV, but captures a different aspect (worst-case deviation vs. spread). Not redundant.

---

## 3. Inequality and dominance metrics

### Worked two-hole example for comparison

Let holes A and B have absolute fluxes $a_A = 9$, $a_B = 1$ (total = 10).

| Metric | Formula | Value |
|--------|---------|-------|
| **CV** | $\sigma / \bar{a}$ | $\frac{4\sqrt{2}}{5} \approx 0.8$ (population std) |
| **Gini** | $\frac{\sum_{i,j}|a_i - a_j|}{2N\sum a_i}$ | $\frac{2 \cdot 8}{2 \cdot 2 \cdot 10} = 0.4$ |

I will compare each new metric against these values.

### 3.1 Theil T Index (GE(1))

$$T = \frac{1}{N_a} \sum_{i=1}^{N_a} \frac{a_i}{\bar{a}} \ln\left(\frac{a_i}{\bar{a}}\right)$$

**Range**: $[0, \ln N_a]$. $T = 0$ means perfect equality. $T = \ln N_a$ means all flux in one hole.

**Worked example**: $\bar{a} = 5$. $T = \frac{1}{2}\left[\frac{9}{5}\ln\frac{9}{5} + \frac{1}{5}\ln\frac{1}{5}\right] = \frac{1}{2}[1.8 \cdot 0.588 + 0.2 \cdot (-1.609)] = \frac{1}{2}[1.058 - 0.322] = 0.368$.

**Comparison with CV and Gini**: Theil $T$ is decomposable — it can be additively split into within-zone and between-zone components:

$$T = T_\text{within} + T_\text{between}$$

where:

$$T_\text{between} = \sum_{z \in \{P,M,D\}} \frac{N_z \bar{a}_z}{N_a \bar{a}} \ln\frac{\bar{a}_z}{\bar{a}}$$

$$T_\text{within} = \sum_{z \in \{P,M,D\}} \frac{N_z \bar{a}_z}{N_a \bar{a}} T_z$$

Neither CV nor Gini allows this exact additive decomposition. This is the key advantage: **Theil T can distinguish whether inequality comes from between-zone differences or within-zone variation.** This is strictly more informative than CV or Gini alone.

**Degenerate case**: If any $a_i = 0$, the $\ln(0)$ term diverges. Convention: exclude inactive holes (use only active set), or replace $\ln(a_i/\bar{a})$ with 0 when $a_i < \varepsilon$.

**Mesh robustness**: Yes.

**Clinical interpretability**: Only with context.

**Use**: Diagnostic feature. The decomposition into within/between is especially valuable for understanding whether the zone structure itself drives inequality, or whether it's intra-zone variation.

---

### 3.2 Max-to-Mean Ratio (Dominance Ratio)

$$R_\text{max} = \frac{\max_i a_i}{\bar{a}} = \frac{N_a \cdot \max_i a_i}{Q_\text{holes}^{\text{abs}}}$$

**Range**: $[1, N_a]$. $R_\text{max} = 1$: all holes equal. $R_\text{max} = N_a$: one hole carries all flux.

**Worked example**: $R_\text{max} = 9/5 = 1.8$.

**Comparison**: CV = 0.8, Gini = 0.4, $R_\text{max}$ = 1.8. $R_\text{max}$ captures how dominant the single strongest hole is — a clinically relevant quantity (is one hole doing all the work?). CV and Gini summarize the full distribution; $R_\text{max}$ focuses on the extreme. For a distribution like $(5, 5, 5, 5, 80)$, $R_\text{max}$ is very high (5.0) while CV and Gini are moderate. This extreme-hole detection is not captured by CV or Gini.

**Degenerate case**: $N_a = 0 \Rightarrow \texttt{NaN}$. $N_a = 1 \Rightarrow 1.0$.

**Mesh robustness**: Yes.

**Clinical interpretability**: Yes — "the most active hole carries 3× the average."

**Use**: Both diagnostic and optimization constraint. A surgeon may not want $R_\text{max} > 3$ to avoid single-point-of-failure drainage.

**Adds information beyond CV/Gini?**: Yes — it is a function of the maximum only, while CV/Gini integrate over the full distribution. A bimodal distribution with moderate CV can have very high $R_\text{max}$.

---

### 3.3 Top-k Dominance Fraction

$$D_k = \frac{\sum_{i=1}^{k} a_{(i)}}{Q_\text{holes}^{\text{abs}}}$$

where $a_{(1)} \geq a_{(2)} \geq \cdots$ are the order statistics.

Recommended default: $k = 3$ (top-3 holes' share of total exchange).

**Range**: $[k/N_a, 1]$. Lower bound attained when all holes are equal; upper bound when $k$ holes carry everything.

**Worked example** ($k = 1$): $D_1 = 9/10 = 0.9$.

**Comparison**: This is equivalent to the cumulative share of the top slice of the Lorenz curve. Gini summarizes the full Lorenz curve; $D_k$ samples it at a specific quantile. $D_k$ is thus a projection of the information in Gini, but often more interpretable ("the top 3 holes carry 70% of exchange").

**Degenerate case**: $N_a < k \Rightarrow D_k = 1.0$ (trivially, fewer holes than $k$).

**Mesh robustness**: Yes.

**Clinical interpretability**: Yes — directly translatable.

**Use**: Diagnostic. Helps answer: "if these top 3 holes occlude (encrust), what fraction of drainage is lost?"

**Adds information beyond CV/Gini?**: Partially redundant with Gini for smooth distributions, but for bimodal or clustered flux distributions, $D_k$ at small $k$ captures tail behavior that Gini and CV compress away.

---

### 3.4 Zone Competition Ratio

$$\mathrm{ZCR} = \frac{\max(Q_P^{\text{abs}}, Q_M^{\text{abs}}, Q_D^{\text{abs}})}{\min^{+}(Q_P^{\text{abs}}, Q_M^{\text{abs}}, Q_D^{\text{abs}})}$$

where $\min^{+}$ is the minimum over zones with at least one active hole (to avoid $0/0$).

**Range**: $[1, \infty)$. $\mathrm{ZCR} = 1$: perfectly balanced zones. Large $\mathrm{ZCR}$: one zone dominates.

**Degenerate cases**:
- Only one zone has active holes: $\mathrm{ZCR} = \texttt{NaN}$ (or $\infty$; prefer NaN).
- Two zones active, one with zero flux: $\mathrm{ZCR} = \texttt{NaN}$ (avoid division by zero).

**Comparison with `CV_Qsh`**: `CV_Qsh` is the CV of the 3-element zone flux vector. $\mathrm{ZCR}$ is a worst-case ratio. For zones $(10, 5, 1)$: $\text{CV} \approx 0.67$, $\mathrm{ZCR} = 10$. $\mathrm{ZCR}$ is more sensitive to extreme imbalance and easier to interpret ("the worst zone gets 10× less than the best").

**Mesh robustness**: Yes.

**Clinical interpretability**: Yes — "the most active zone drains 5× more than the least active."

**Use**: Diagnostic feature and potential optimization constraint.

**Adds information beyond CV?**: Yes — $\mathrm{ZCR}$ is sensitive to extreme-zone-dominance in a way that the 3-sample CV is not. CV compresses the distinction between $(10, 9, 1)$ and $(10, 5, 5)$; ZCR amplifies it.

---

## 4. Reduced-order descriptors for GP surrogate learning

### 4.1 Is the proximal/mid/distal triplet redundant?

**Yes, given total hole flux and two localization descriptors.**

The triplet $(Q_P, Q_M, Q_D)$ lives on a 2-simplex (they sum to $Q_\text{holes}^{\text{abs}}$). This means it has **2 degrees of freedom** beyond the total, not 3. Specifically:

$$Q_P = Q_\text{holes}^{\text{abs}} \cdot f_P, \quad Q_M = Q_\text{holes}^{\text{abs}} \cdot f_M, \quad Q_D = Q_\text{holes}^{\text{abs}} \cdot (1 - f_P - f_M)$$

So the **minimal non-redundant encoding** of the zone triplet is:

1. $Q_\text{holes}^{\text{abs}}$ — total magnitude
2. Any two of $(f_P, f_M, f_D)$ — simplex coordinates

Alternatively, one could use:
1. $Q_\text{holes}^{\text{abs}}$
2. Flux centroid $\hat{x}/L$ — captures the mean location (approximately encodes $f_P$ vs $f_D$)
3. Flux IQS or spread — captures how concentrated vs distributed

This second representation has the advantage that centroid and spread are **continuous** functions of hole positions and fluxes (unlike zone fractions, which are discontinuous at zone boundaries when a hole moves from mid to prox). For a GP with a stationary kernel, continuous inputs are preferable.

**Recommendation**: Replace `(prox_hole_abs_flux, mid_hole_abs_flux, dist_hole_abs_flux)` with `(Q_holes_abs, centroid_normalized, IQS)` or equivalently `(Q_holes_abs, f_P, f_M)`. The former is preferable if hole positions vary continuously; the latter if zone boundaries are fixed and zone identity is the relevant clinical concept.

---

### 4.2 Signed vs absolute flux: joint or separate GP targets?

**Separate targets are preferable**, for two reasons:

1. **Sign structure**: Absolute flux $a_i$ is always non-negative. Signed flux $q_i$ can be positive or negative. A GP with a Matérn kernel assumes the output varies smoothly; the absolute value function introduces a non-differentiable kink at zero. If some designs have near-zero flux through a hole (so $q_i$ crosses zero), the GP will struggle to model both $|q_i|$ and $\text{sign}(q_i)$ simultaneously.

2. **Information content**: For the surrogate used in optimization, the relevant quantities are typically absolute exchange magnitudes and the net direction index $\mathrm{NDI}$. Model $Q_\text{holes}^{\text{abs}}$ (or zone-level absolute fluxes) as the primary GP target. If net direction matters, add $\mathrm{NDI}$ as a separate scalar target.

**Recommendation**: Use absolute flux aggregates as GP targets. Add NDI as a separate output if directionality is decision-relevant. Do not model per-hole signed fluxes as GP targets (too high-dimensional, too noisy).

---

### 4.3 Single scalar capturing both magnitude and spatial distribution?

**Possible but not recommended as a sole target.** A candidate:

$$S = Q_\text{holes}^{\text{abs}} \cdot (1 - D_\text{KS})$$

This rewards high total exchange with uniform spatial distribution. But it conflates two objectives that may trade off against each other, destroying Pareto information. A GP trained on $S$ cannot distinguish "high exchange, poor distribution" from "low exchange, good distribution."

**Recommendation**: Keep magnitude and distribution as **separate** GP outputs. Use scalarization only at the acquisition-function level (which your optimizer already does via `ScalarizedPosteriorTransform`).

---

### 4.4 Recommended transforms for GP targets

| Metric | Distribution shape | Recommended transform | Rationale |
|--------|-------------------|----------------------|-----------|
| $Q_\text{out}$ | Positive, potentially right-skewed | $\log(Q_\text{out})$ | Log-normal is common for flow rates; stabilizes variance |
| $\Delta P$ | Positive, potentially right-skewed | $\log(\Delta P)$ | Same reasoning; also spans orders of magnitude across designs |
| $Q_\text{holes}^{\text{abs}}$ | Non-negative, right-skewed | $\log(Q_\text{holes}^{\text{abs}} + \varepsilon)$ | Add small $\varepsilon$ for designs with zero exchange |
| $\mathrm{Ex}$ | Positive, bounded below by 0 | $\log(\mathrm{Ex} + \varepsilon)$ | |
| $G^*$ | Positive | $\log(G^*)$ | |
| $\hat{x}/L$ (centroid) | Bounded $[0, 1]$ | $\text{logit}(\hat{x}/L)$ | Maps $(0,1)$ to $\mathbb{R}$; natural for a proportion |
| $\mathrm{IQS}$ | Bounded $[0, 1]$ | $\text{logit}(\mathrm{IQS})$ | Same |
| $f_P, f_M$ | Bounded $[0,1]$, sum-constrained | ILR (isometric log-ratio) on the simplex $(f_P, f_M, f_D)$ | The proper transform for compositional data; produces 2 unconstrained reals |
| $\mathrm{NDI}$ | Bounded $[-1, 1]$ | $\text{arctanh}(\mathrm{NDI})$ (Fisher z) | Maps $(-1,1)$ to $\mathbb{R}$ |
| CV | Non-negative, unbounded | $\log(\text{CV} + \varepsilon)$ | Right-skewed |
| $R_\text{max}$ | $[1, N_a]$ | $\log(R_\text{max})$ | |
| $T$ (Theil) | $[0, \ln N_a]$ | None or $\sqrt{T}$ | Mild skew; sqrt often sufficient |
| $D_\text{KS}$ | Bounded $[0, 1]$ | $\text{logit}(D_\text{KS})$ | |

**Key principle**: Use $\log$ for positive unbounded quantities, $\text{logit}$ for proportions in $(0,1)$, ILR for simplicial data, and $\text{arctanh}$ for quantities in $(-1,1)$. These transforms make the GP's stationarity assumption (constant marginal variance) more plausible.

**Degenerate case handling**: When a metric hits its boundary value (e.g., $\mathrm{IQS} = 0$ or $\mathrm{NDI} = \pm 1$), logit/arctanh diverge. Convention: clamp to $[\varepsilon, 1-\varepsilon]$ or $[-1+\varepsilon, 1-\varepsilon]$ before transforming. Use $\varepsilon = 10^{-6}$.

---

## Recommended minimal non-redundant output set

### Replace current correlated multi-output targets with:

**Current GP target set** (inferred): `{Q_out, deltaP, prox_hole_abs_flux, mid_hole_abs_flux, dist_hole_abs_flux, Q_holes_abs, hole_uniformity_cv}` — 7 outputs, highly correlated (zone triplet sums to Q_holes_abs; CV is a function of the per-hole distribution which determines zone totals).

**Proposed minimal set** (5 outputs, lower correlation):

| # | Metric | Symbol | Transform | Role |
|---|--------|--------|-----------|------|
| 1 | Pressure drop | $\Delta P$ | $\log$ | Primary objective |
| 2 | Total outlet flow | $Q_\text{out}$ | $\log$ | Primary objective |
| 3 | Exchange Number | $\mathrm{Ex}$ | $\log$ | Replaces `Q_holes_abs` (which is $\mathrm{Ex} \cdot Q_\text{out}$, recoverable) |
| 4 | Normalized flux centroid | $\hat{x}/L$ | logit | Replaces zone triplet's "where" information |
| 5 | Flux IQS | $\mathrm{IQS}$ | logit | Replaces zone triplet's "how spread" information + partially replaces CV |

**Information loss assessment**:
- Zone triplet is recoverable from centroid + IQS + total only approximately (not exactly), because two moments don't uniquely determine a 3-bin histogram. However, for the purpose of a GP surrogate with ~60-200 training points, the approximation is likely better than the correlation penalty from carrying 3 extra outputs.
- CV is partially captured by IQS and the per-hole distribution's higher moments, but not exactly. If per-hole inequality is a primary concern, add $R_\text{max}$ as output #6.

**Optional additions** (upgrade to 6-7 outputs if data budget permits):

| # | Metric | When to add |
|---|--------|-------------|
| 6 | $R_\text{max}$ (max-to-mean ratio) | When single-hole dominance is a failure mode |
| 7 | $\mathrm{NDI}$ (net direction index) | When directionality matters for clinical outcomes |

**Why this is better than the current set**:
1. **Lower dimension**: 5 vs 7 outputs → better GP conditioning with limited data.
2. **Lower correlation**: $\log \mathrm{Ex}$ is approximately uncorrelated with $\log Q_\text{out}$ and $\log \Delta P$ when designs vary primarily in hole geometry. The zone triplet is perfectly correlated with its own sum.
3. **Continuous in hole positions**: Centroid and IQS vary smoothly as holes shift; zone fractions are discontinuous at zone boundaries.
4. **Transform-ready**: Each metric has a natural variance-stabilizing transform that respects its domain.

---

## Open uncertainties

1. **ILR vs logit for zone fractions**: If the clinical team insists on zone-level outputs (because zone identity maps to anatomical landmarks), the simplex should use ILR coordinates rather than raw fractions. But ILR requires all three zones to be active; if a design has zero distal holes, the simplex collapses to a face. Convention for this edge case needs to be decided.

2. **Mesh convergence of conductance**: $G^*$ involves $Q_\text{out}/\Delta P$; both are mesh-sensitive at coarse resolutions. The ratio partially cancels bias but not variance. A mesh refinement study should validate that $G^*$ converges faster than either component alone.

3. **Kurtosis reliability at small $N_a$**: The axial flux kurtosis ($\gamma_2$) requires $N_a \geq 6$ to be statistically meaningful. Many designs in the current parameter space may have $N_a < 6$ (e.g., 3 mid holes + 0 prox). Recommend not using $\gamma_2$ as a GP target until campaigns with denser hole patterns are run.

4. **Theil decomposition with empty zones**: If a zone has zero active holes, $T_z$ is undefined. Convention: exclude empty zones from the decomposition and note the effective number of active zones. This changes the interpretation of $T_\text{between}$.

5. **NDI stability near zero**: When total hole exchange is near zero, $\mathrm{NDI}$ becomes noisy (small denominator). The $\varepsilon$-thresholding in `active_eps_ml_min` prevents exact zero, but very small $Q_\text{holes}^{\text{abs}}$ still produces unreliable $\mathrm{NDI}$. Recommend: set $\mathrm{NDI} = \texttt{NaN}$ when $Q_\text{holes}^{\text{abs}} < 10 \varepsilon$.

6. **Unroof-conditional metrics**: $\mathrm{Ex}$ includes unroof flux. For designs without an unroof patch (`unroofed_length = 0`), $\mathrm{Ex} = \mathrm{Ex}_h$. This is well-defined. But for GP training, mixing unroofed and non-unroofed designs in the same target may create a discontinuity. Consider: training separate GPs for unroofed vs non-unroofed campaigns, or including `unroofed_length` as an input feature and accepting the interaction.

7. **CV ambiguity**: The codebase has `hole_uniformity_cv` (per-hole) and `CV_Qsh` (per-zone, 3-sample). These are different quantities with different statistical properties. The per-zone CV has only 3 samples and is inherently noisy. Recommend: use only `hole_uniformity_cv` as a GP target; deprecate `CV_Qsh` or use it only as a diagnostic.

8. **Counterexample for zone CV as optimization target**: Two designs: (A) 6 prox holes each with flux 5, 6 mid holes each with flux 5, 6 distal holes each with flux 5 → zone CV = 0, per-hole CV = 0. (B) 1 prox hole with flux 30, 1 mid hole with flux 30, 1 distal hole with flux 30 → zone CV = 0, per-hole CV = 0. Designs A and B have identical CV at both levels, but A has distributed drainage across 18 holes while B concentrates on 3 holes. $R_\text{max} = 1$ for both, but $\mathrm{Ex}$ differs (higher for A if same $Q_\text{out}$). This illustrates that no single inequality metric is sufficient — you need both a uniformity metric (CV) and a coverage/exchange metric (Ex or $n_\text{active}$).

9. **Sign convention validation**: The current sign convention (positive = into lumen) means that for a pressure-driven flow from inlet to outlet, most hole fluxes should be positive (CSF enters through side holes into the lumen). This should be validated against the first real COMSOL run. If the convention is reversed in the COMSOL template (e.g., due to outward-pointing measurement-surface normals), $\mathrm{NDI}$ will have flipped sign. The `sign_convention` field in `meters.json` must be checked against actual simulation output.
