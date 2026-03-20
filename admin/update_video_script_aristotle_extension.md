# Update Video Script: Formal Verification and Surrogate Integrity

I want to add a crucial addendum to the previous update on our objective-function architecture.

In the last update, I explained that we train our Gaussian Process surrogate on a transformed Tier-1 state $\tilde{y}$ rather than raw, mixed-unit COMSOL outputs. I outlined how moving to log and logit scales creates a state-space where the marginal log-likelihood loss $\mathcal{L}_{\mathrm{GP}}(\theta)$ and the resulting predictive density assumptions are actually defensible.

But that architecture hides a massive vulnerability if left alone. The GP is entirely blind to the physics of the data it absorbs. It assumes that the dependent variables $Y$ are drawn from a stationary process parameterized by a Matérn $5/2$ kernel over the design matrix $X$. 

If the underlying simulation pipeline quietly outputs a non-converged solver state, or a state where mass balance is violated ($Q_{\mathrm{in}} + Q_{\mathrm{out}} \gg 0$), the GP does not know that. It interprets that physical failure as a legitimate, extreme gradient in the objective landscape. That destroys the covariance structure of the surrogate. A single unflagged mass-balance failure can permanently ruin the posterior predictive variance $\sigma^2$ in that region of the design space, rendering the expected-improvement acquisition function $\alpha_{\mathrm{EI}}(x)$ completely useless.

To solve this, we cannot just rely on `assert` statements in pandas. We need a mathematically rigorous gate between the raw empirical extraction and the surrogate training set. 

This is why we have introduced a formally verified schema layer using the Lean 4 theorem prover. We are now treating the measurement contract itself—the actual mapping from COMSOL to CSV—as a formal mathematical object.

### The Formalized Measurement Contract

When the pipeline exports `feature_flux_long.csv` and `design_outputs.csv`, it generates a set of rows. We have mapped those structurally into Lean as `FeatureFluxRow` and `DesignSummaryRow`.

Instead of just hoping the extraction script did its math correctly, the formalization defines *consistency predicates*. For instance, a basic measurement consistency requires:

$$
a_i = |q_i|, \qquad A_i \ge 0.
$$

If a row in the feature table claims an absolute flux that does not match the signed flux magnitude, or a negative measurement area, it is formally rejected.

More importantly, the formalization encodes the strict "Tier 1" consistency of the macroscopic design summary. For a summary row to be considered `tier1Consistent`, it must simultaneously satisfy a system of invariants, such as:

$$
\Delta P = p_{\mathrm{in,avg}} - p_{\mathrm{out,avg}},
$$
$$
Q_{\mathrm{holes}}^{\mathrm{abs}} = \pi_{\mathrm{prox}} + \pi_{\mathrm{mid}} + \pi_{\mathrm{dist}},
$$
$$
Q_{\mathrm{exchange}}^{\mathrm{abs}} = Q_{\mathrm{holes}}^{\mathrm{abs}} + Q_{\mathrm{unroof}}^{\mathrm{abs}}.
$$

These are not unit tests. They are formal proofs that the pipeline’s structural aggregation operations match the physical conservation laws.

### The Quality Control Gate and Edge Cases

This brings us to the operational bridge protecting the GP. The formalized layer defines a Quality Control (QC) predicate:

$$
\mathrm{passesQC}(s) := (\mathrm{solverConverged} = \mathrm{true}) \land (|\varepsilon_{\mathrm{mass}}| \le \epsilon_{\mathrm{tol}}).
$$

Here, $\varepsilon_{\mathrm{mass}}$ is the relative mass balance error.

The central theorem of this new schema layer, proved exhaustively in Lean without any deferred assumptions, is the bridge theorem:

$$
\mathrm{passesQC}(s) \implies \mathrm{ValidSample}(s).
$$

What this theorem states is that passing the pipeline's QC gate is *mathematically sufficient* to lift an empirical row into a valid abstract sample. It guarantees that all downstream metric derivations—such as the flux centroid $\bar{x}_{\mathrm{flux}}$, the exchange spread, and the dimensionless exchange number $\mathrm{Ex}$—are safely computable. 

This is incredibly important for handling edge cases like degenerate geometric failures (e.g., zero active holes, or cases where the unroof patch dominates 100% of the exchange). Without this formal guarantee, edge cases could trigger silent divide-by-zero errors in the objective calculation, leaking `NaN`s into the GP training set. The proofs in Lean explicitly cover these coordinate-collapse scenarios, guaranteeing that the bounding wrappers map degeneracies safely into defined limits (for instance, mapping spread to $0$ when all active points share a common coordinate).

### Why This Matters for the Pipeline

If I synthesize this into the broader pipeline narrative, the introduction of Lean 4 means our data-generation loop is now fundamentally mathematically strict.

1. **Geometry Generation** restricts $x$ to the physically realizable $\mathcal{X}_{\mathrm{feasible}}$.
2. **COMSOL** produces a realized field state $(u, p)$.
3. **The Extraction Layer** maps the continuous field to discrete flux descriptors $\phi(x)$.
4. **The Lean Schema** mathematically verifies that $\phi(x)$ satisfies conservation, strict consistency, and QC invariants. Invalid states are dropped.
5. **The Surrogate** trains *only* on the verified subspace, guaranteeing that the Gaussian distributional assumptions on the transformed state $\tilde{y}$ are valid, stationary, and uncorrupted by solver hallucination.

In short, rather than training an "intelligent" surrogate on naive, unverified physics outputs, we are actively filtering the state-space through a formalized mathematical proof layer. This ensures that when the acquisition function tells us to sample a particular design next, it is doing so based on a rigorously sound interpretation of the fluid mechanics, not an artifact of bad extraction logic.
