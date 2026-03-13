# Full Breakdown of `2339.pdf`

## Paper identity
- **Title:** Multicondition and multimodal temporal profile inference during mouse embryonic development
- **Core method:** **Sunbear**
- **Model family:** Conditional variational autoencoder (cVAE) with continuous-time encoding
- **Primary biological system:** Mouse embryonic development
- **Primary data types:** scRNA-seq and scATAC-seq time-series (plus coassay data for alignment)

---

## 1) What problem the paper is solving

### The practical bottleneck
Single-cell measurements are destructive. You cannot measure the same cell again later in time. So for a given cell, you only see one snapshot.

### Why existing methods are incomplete
Many methods can do one of these well:
- infer trajectories in one modality,
- align cells across neighboring time points,
- integrate batches/conditions,
- or do cross-modal translation.

But they generally do **not** jointly do all of the following in one framework:
- infer missing time points,
- across different conditions (e.g., sex),
- across different modalities (e.g., RNA and ATAC),
- at single-cell resolution.

### Sunbear's stated aim
Given a single-cell profile, estimate what that profile would look like if measured:
- at another time point,
- in another condition,
- and/or in another modality.

This is the central counterfactual inference task of the paper.

---

## 2) The core idea of Sunbear

Sunbear learns a factorized latent representation with separate roles:
- **Cell identity embedding**: latent cell state intended to be time-invariant and condition-invariant.
- **Time factor**: sinusoidal embedding of continuous time.
- **Condition factor**: one-hot (sex, etc.).
- **Batch factor**: one-hot for technical effects.

Then it reconstructs data by combining these factors in the decoder.

### Why sinusoidal time encoding
Using sinusoidal functions gives a continuous and periodic basis over time, allowing interpolation at missing times better than using a raw scalar time input.

### Why the adversarial/discriminator piece matters
They add a time discriminator on the learned cell embedding and train adversarially so the embedding carries less explicit time information. This is critical for “hold cell identity fixed, swap time” inference.

---

## 3) Mathematical and modeling details (from Methods)

## 3.1 Single-modality model (RNA)
- Uses cVAE framework.
- Observation model for scRNA-seq: **ZINB** (zero-inflated negative binomial).
- Loss has two major pieces:
  - reconstruction log-likelihood (ZINB),
  - KL divergence regularization for latent distribution.

Form reported in paper:
- `loss_RNA = -zinb.loglik(RNA_true, RNA_pred) + D_KL[Q(z|X,t) || P(z,t)]`

Then adversarial training:
- discriminator predicts time from `z`: `loss_DIS = CE(discriminator(z), t)`
- generator uses: `loss_GEN = loss_RNA - loss_DIS`

### Intuition
- Reconstruction forces informative latent structure.
- KL regularizes latent space.
- Adversarial term discourages time leakage into cell embedding.

## 3.2 Multimodal extension (RNA + ATAC)
For scATAC-seq:
- binarized accessibility,
- Bernoulli likelihood with **binary cross-entropy (BCE)** reconstruction.

Reported form:
- `loss_ATAC = -BCE(ATAC_true, ATAC_pred) + D_KL[...]`

Joint constraints:
- shared time-relevant interaction layer,
- embedding alignment between modalities (MSE on coassay-matched cells),
- translation losses between modalities.

This architecture lets RNA (denser time sampling) guide ATAC (sparser time sampling).

## 3.3 Key default hyperparameters
- Cell latent dimension: 50 (tuned over {25, 50, 100})
- Time encoding dimension: 50
- Hidden layer width: geometric mean of input and latent dims
- Multimodal MSE weight `λ` tuned over {1, 100, 10000}

---

## 4) Data and evaluation design

## 4.1 Data scope
Major time-series sources include:
- Qiu et al. 2024 (very large embryo time series; subsampled to 1M cells for training efficiency)
- Pijuan-Sala et al. 2019
- Qiu et al. 2022
- Cao et al. 2019
- Argelaguet et al. 2022 coassay RNA+ATAC

## 4.2 Validation strategy
Because no repeated measurements of the same single cell over time are possible, they evaluate with proxy strategies:
- cell-type-level pseudobulk correlation,
- AUROC for directionality tasks (differential expression/accessibility),
- comparisons to nearest-time baselines,
- matched-sex-time points where available for external validation.

## 4.3 Important metric interpretations
- **Pseudobulk Pearson correlation:** how well predicted cell-type mean profile matches held-out truth.
- **AUROC:** ranking quality for positive vs negative differential signals.
- **AUPRnorm:** precision-recall adjusted for class imbalance.
- **LISI:** integration quality across batches/time/modality.

---

## 5) Results section, fully broken down

## 5.1 Sunbear model overview (Figure 1 context)
They define training and inference mechanics, then show Sunbear can:
- model continuous time,
- condition swap (e.g., sex),
- modality swap (RNA->ATAC),
- and joint multimodal temporal inference.

## 5.2 Simulation checks
Two simulation scenarios:
- high-noise temporal trend recovery,
- unsynchronized pseudotime per cell-type to test heterogeneity capture.

Conclusion: Sunbear can recover temporal patterns and cell-level variation.

## 5.3 Missing-time and missing-condition inference (Figure 2)
They hold out one time point at a time and test:
- cross-time inference from neighboring time points,
- cross-sex inference using opposite sex as query,
- stricter baseline using average of neighboring time points.

Outcome:
- Sunbear generally beats nearest-time baselines in pseudobulk correlation.
- Works even when data become temporally sparser.
- Also outperforms TrajectoryNet in their sparse-time comparison.

## 5.4 Sex-biased transcription discovery (Figure 3)
After validating prediction quality, they use Sunbear to estimate sex-biased expression over developmental time.

Key claims:
- Better recapitulation of known sex-biased patterns than baseline.
- Better ranking of known constitutive X-escape genes as female-biased.
- Strong female bias signals include **Xist**, **Kdm6a**, and other escape genes.
- Macrophages show stronger and richer sex bias signatures than glutamatergic neurons.
- Female-biased autosomal genes in macrophages show immune-process enrichment.

## 5.5 Multimodal temporal inference and chromatin-priming dynamics (Figure 4)
They hold out ATAC time points and predict accessibility using RNA or ATAC queries.

Findings:
- alignment across modality/batch/time appears good in embedding space,
- temporal differential accessibility direction is predicted well,
- single-cell-level peak accessibility trends are recovered for >99.9% of peaks (by their criterion),
- TLCC analysis suggests a gradient of lag relationships:
  - some peaks change before nearby gene expression,
  - some after,
  - implying heterogeneous regulatory timing rather than one fixed lag.

Motif analysis in "before" regions highlights factors including CTCF, ZIC2, ZIC3, matching known hindbrain biology narratives.

---

## 6) Discussion points (what the authors claim vs what is actually supported)

## What is strongly supported in-paper
- Sunbear can improve held-out temporal/condition profile reconstruction against nearest-time baselines in their settings.
- Joint modality-condition-time modeling is feasible at scale.
- Model can generate biologically coherent hypotheses (sex-bias programs, chromatin priming patterns).

## What is still inferential
- True single-cell longitudinal causality is not directly observed (still snapshot inference).
- TLCC-based lag relationships are correlative model-derived quantities, not direct perturbational proof.
- Dependence on coassay data for strongest multimodal alignment is acknowledged by authors.

## Limits explicitly acknowledged
- Could improve with explicit proliferation/death modeling.
- Current multimodal approach uses coassay guidance; full no-coassay generalization is future work.
- Assumes relatively smooth temporal change between sampled points.

---

## 7) Deep figure-by-figure explanation

## Figure 1: Sunbear framework
### Panel A: Input geometry and missingness structure
- Top block: biological conditions (female/male) observed at partially mismatched times.
- Bottom block: modality mismatch (RNA dense vs ATAC sparse).
- Visual point: missingness is structured, not random; that structure is what Sunbear models.

### Panel B: Representation decomposition and training logic
- Inputs are decomposed into cell embedding + time + condition + batch.
- Time uses sinusoidal encoding.
- RNA and ATAC encoders/decoders run in parallel with alignment constraints.
- Shared time-interaction layer is key to transfer temporal signal from dense modality (RNA) to sparse modality (ATAC).

### Panel C: Counterfactual generation mode
- Hold cell identity fixed, vary time -> temporal trajectory prediction.
- Swap condition -> cross-condition counterfactual (e.g., female vs male profile for same latent cell state).
- Cross-modality decode -> predict missing modality trajectories.

### Why this figure matters
This is the entire paper in one picture: decomposition, alignment, and conditional generation.

---

## Figure 2: Cross-time and cross-sex performance
### Panel A
- Shows alternating-sex sampling across developmental time.
- Makes direct sex comparison impossible at most time points without modeling.

### Panel B
- Three evaluation schemes:
  - cross-time,
  - cross-sex,
  - cross-sex strict baseline.
- The held-out block design clarifies what information is truly unavailable during training.

### Panels C, D, E (scatter plots)
- Axes compare Sunbear vs baseline correlation to held-out pseudobulk truth.
- Points above diagonal = Sunbear better.
- Reported counts and one-sided Wilcoxon P-values support consistent improvement.

### Signal-level interpretation
- Gains are largest where nearest-time extrapolation is weak.
- Method remains useful in sparse time settings, which is critical for expensive or slow experiments.

---

## Figure 3: Sex differences during development
### Panel A
- AUROC comparison for identifying female-/male-biased genes against matched-sex truth.
- Sunbear outperforms nearest-time baseline.

### Panel B
- Escape-gene ranking test: can model prioritize known constitutive X-escape genes as female-biased?
- Sunbear performs substantially better than baseline differential expression from sparse original snapshots.

### Panels C and D
- Temporal log fold-change trajectories in glutamatergic neurons vs border-associated macrophages.
- Escape genes show persistent female bias across time.
- Macrophages show broader X-linked female-biased patterns than neurons.

### Panel E
- Biological external check via `Kdm6a` KO signatures.
- Genes down in KO (candidate KDM6A-activated set) skew toward female-biased scores in macrophages.

### Panel F
- GO enrichment for consistent sex-biased genes.
- Macrophages: strong immune-related enrichment.
- Glutamatergic neurons: no strong process-level enrichment in this analysis.

### Biological thesis from Figure 3
Sex-biased developmental transcription is not only about X-linked genes; autosomal programs appear coordinated with escape-gene biology, especially in immune lineage contexts.

---

## Figure 4: Multimodal temporal inference and lag structure
### Panel A
- UMAP demonstrates integration quality across modality and dataset at overlapping time points.
- Good colocalization is prerequisite for meaningful cross-modal imputation.

### Panel B
- AUROC for predicting differential accessibility between query and held-out time points.
- Both RNA and ATAC query modes perform above random in most comparisons.

### Panel C
- Peak-wise AUROC across all cells for predicting held-out ATAC from RNA queries.
- Demonstrates cell-level heterogeneity capture beyond pseudobulk averages.

### Panel D
- Workflow figure for TLCC computation:
  - predict continuous RNA + ATAC curves from query cell,
  - shift accessibility curve relative to expression,
  - compute correlation over lags,
  - summarize each peak-gene pair as a lag-correlation vector.

### Panel E
- Heatmap of lag structure for many peak-gene pairs.
- Shows a continuum, not a single fixed delay.
- “Before” and “after” categories operationalize potential priming vs trailing accessibility dynamics.

### Biological interpretation
- Supports known priming concept (accessibility often precedes expression),
- but also reveals heterogeneity in lag sign and magnitude,
- suggesting lineage-specific regulatory timing architecture.

---

## 8) Why this paper is technically important

- Unifies condition modeling, temporal interpolation, and modality translation in one trainable framework.
- Scales to very large single-cell datasets.
- Produces actionable biological hypotheses when direct matched measurements are impossible.

---

## 9) Critical reading checklist (for discussion/Q&A)

- Ask how robust results are to alternate cell-type annotation granularity.
- Ask whether stronger baselines (state-of-the-art multimodal time methods) would shrink gains.
- Ask where uncertainty quantification of predictions is surfaced to users.
- Ask what breaks first under extreme temporal sparsity.
- Ask how much coassay supervision is minimally required for reliable RNA->ATAC transfer.

---

## 10) One-paragraph summary

Sunbear is a cVAE-based framework that factorizes single-cell profiles into cell identity, time, condition, and batch components, enabling counterfactual prediction across missing time points, biological conditions, and modalities. In mouse embryonic datasets, it improves held-out profile reconstruction over nearest-time baselines, supports sex-bias discovery (including escape-gene-consistent signals), and enables multimodal temporal analyses that suggest heterogeneous lag relationships between chromatin accessibility and transcription. The approach is powerful for hypothesis generation under destructive sampling constraints, while remaining inferential rather than directly causal at true longitudinal single-cell level.
