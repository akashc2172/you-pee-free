# 30-Minute Speaker Script: Sunbear (Paper `2339.pdf`)

## Timing map
- Slide 1: 2:00
- Slide 2: 2:30
- Slide 3: 2:30
- Slide 4: 3:30
- Slide 5: 2:45
- Slide 6: 2:45
- Slide 7: 2:30
- Slide 8: 2:45
- Slide 9: 2:15
- Slide 10: 2:15
- Slide 11: 2:00
- Slide 12: 1:15
- Slide 13: 1:00

Total planned talk time: **30:00**.

---

## Slide 1 (2:00) - Title and thesis

### Script
Today I’ll walk through a paper that tries to solve one of the hardest practical problems in single-cell biology: we only get snapshot data, but we want temporal behavior. The paper introduces **Sunbear**, a model that infers missing single-cell profiles across time, across conditions like sex, and across modalities like RNA and ATAC.

The core thesis is this: if we can separate latent **cell identity** from **time**, **condition**, and **batch**, then we can hold identity fixed and change the other factors to generate counterfactual profiles. That gives us a computational way to ask: what would this cell look like at a different stage, in the opposite sex, or in another modality?

In this talk, I’ll do three things: first, unpack the model mechanics in plain but rigorous terms; second, read Figures 1 through 4 panel by panel; and third, separate what the paper strongly proves from what is still inferential.

### Transition line
Let’s start with why this is technically difficult in the first place.

---

## Slide 2 (2:30) - Why the problem is hard

### Script
The bottleneck is destructive measurement. In almost all single-cell assays, once a cell is measured, it’s gone. So we do not have true same-cell longitudinal tracks. We only have populations sampled at different time points.

Now add the real-world complications. First, time points are not always matched across conditions, like female and male embryos. Second, modality coverage is uneven: RNA is often dense across time, while ATAC is much sparser. Third, batch effects are unavoidable and can dominate signal.

Most existing methods handle one or two axes well, but not all at once. Some align neighboring time points, some do trajectory inference, some do cross-modality translation. The paper’s claim is that we need one integrated model that handles time, condition, and modality jointly.

The question the model operationalizes is very specific: if latent identity is stable, can we alter only time or condition factors and recover realistic profiles in missing blocks?

### Transition line
Next, I’ll show how their experimental setup and metrics are built around that exact question.

---

## Slide 3 (2:30) - Data and evaluation logic

### Script
The paper uses large mouse embryonic time-series datasets, including a very large RNA dataset that they subsample to one million cells for efficiency, plus additional RNA datasets and a coassay RNA+ATAC dataset.

The evaluation is built around leave-one-block-out logic. They hold out entire time points, or time-by-sex blocks, or ATAC blocks at certain time points, and ask whether Sunbear can recover those held-out profiles.

A key limitation is unavoidable: because true same-cell longitudinal ground truth does not exist, they evaluate using cell-type-level pseudobulk agreement and ranking metrics like AUROC. That’s not perfect, but it is a defensible proxy.

On the objective side: for RNA they use ZINB reconstruction plus KL regularization plus adversarial pressure to remove time information from identity embeddings. For ATAC they use BCE-style reconstruction with additional cross-modal alignment and translation constraints.

### Transition line
With that setup in mind, Figure 1 gives the conceptual model blueprint.

---

## Slide 4 (3:30) - Figure 1 full architecture

### Script
Figure 1 is the whole paper compressed into one graphic. Panel A defines the missing-data geometry. In the top part, conditions like female and male are sampled at different time points. In the bottom part, RNA is sampled densely but ATAC is sparse.

Panel B shows the architecture. They encode each cell into latent factors: identity, time, condition, and batch. Time is encoded with a sinusoidal basis, which gives continuous interpolation behavior instead of treating time as just a single scalar bucket.

The critical design move is multimodal coupling. RNA and ATAC branches are constrained so that corresponding cells align in latent space, and time-relevant interaction structure is shared. So dense RNA time information can inform sparse ATAC inference.

Panel C then shows inference mode: take a query cell’s identity, swap time and condition vectors, and decode the profile you want. In multimodal mode, you can also decode into another modality.

Conceptually, this is counterfactual generation under a factorized latent representation.

### Transition line
Now let’s zoom into each panel and spell out what assumptions are hidden there.

---

## Slide 5 (3:00) - Figure 1 deep panel mechanics

### Script
Starting with Panel A: this is not random missingness. It is structured missingness by design. That matters because nearest-neighbor imputation can fail when gaps are systematic.

Panel B carries the main assumption of the entire paper: latent identity can be made relatively invariant to time and condition. The discriminator is important here. It tries to predict time from identity embeddings; the generator is trained to make that prediction harder. If this works, identity becomes a better anchor for temporal swapping.

Panel C operationalizes usage. You do not re-infer everything from scratch each time. You keep identity fixed and manipulate time and condition embeddings. That makes the model interpretable as a controlled simulator, not only a black-box predictor.

Two caveats to state clearly in presentation: one, invariance is never perfect; two, if identity and time are deeply entangled biologically, this decomposition can blur some real effects.

### Transition line
Figure 2 tests whether this machinery actually improves held-out reconstruction.

---

## Slide 6 (3:00) - Figure 2 full view

### Script
Figure 2 evaluates the core claim in practical held-out scenarios. Panel A shows the alternating-sex sampling setup, which motivates why direct sex comparisons are often impossible without imputation.

Panel B sets up three validations: cross-time, cross-sex, and strict cross-sex baseline. In each case, one block is withheld and the model predicts that block using available query blocks.

Panels C, D, and E are the key result visuals. They compare baseline versus Sunbear using pseudobulk Pearson correlation to held-out truth. Above diagonal means Sunbear wins.

What we see broadly is a consistent upward trend above diagonal in many settings, including cross-sex. That suggests the model is capturing transferable temporal structure rather than simply memorizing nearest time points.

### Transition line
Let me decode exactly what each scatter plot is telling us statistically and biologically.

---

## Slide 7 (3:00) - Figure 2 deep interpretation

### Script
These scatter plots are easy to misread, so I’ll be precise. Each dot is a cell trajectory at a held-out time point. x-axis is baseline agreement with held-out truth. y-axis is Sunbear agreement with held-out truth.

If a point sits above the diagonal, Sunbear has a higher correlation than baseline for that trajectory and holdout scenario. The reported counts and one-sided Wilcoxon tests support a consistent positive shift.

Cross-time improvements show that Sunbear adds value beyond local interpolation from nearest neighbors. Cross-sex improvements are more demanding because they include both temporal shift and condition shift; the fact that performance remains above baseline is important.

In strict cross-sex settings, where baseline uses averaged neighboring profiles, margins shrink but remain favorable in many cases. I would present this as evidence of robustness, not perfection.

### Transition line
After technical validation, Figure 3 asks what biology we can discover with these inferred profiles.

---

## Slide 8 (3:00) - Figure 3 full view

### Script
Figure 3 moves from benchmarking to biological discovery: sex-biased expression dynamics during embryonic development.

Panel A validates differential expression pattern recovery with AUROC. Panel B checks whether known constitutive X-escape genes are ranked correctly as female-biased compared with other X-linked genes.

Panels C and D show temporal sex-biased log fold changes for glutamatergic neurons and border-associated macrophages. Panel E cross-checks with Kdm6a knockout-associated gene behavior. Panel F shows GO enrichment patterns.

The broad biological story is that sex-biased expression exists in early development and is stronger in certain lineages, especially macrophage-related contexts.

### Transition line
Now I’ll walk through each Figure 3 panel as a chain from validation to mechanism-level hypothesis.

---

## Slide 9 (2:30) - Figure 3 deep interpretation

### Script
Panel A says Sunbear better recapitulates matched-sex differential patterns than nearest-time baseline. Panel B is especially persuasive because it tests prior biological knowledge: known X-escape genes should trend female-biased, and Sunbear ranks them accordingly.

Panels C and D show sustained female-biased signals from genes like Xist and Kdm6a. The contrast between macrophages and glutamatergic neurons is important: macrophages show broader, stronger sex-biased structure.

Panel E links to Kdm6a biology: genes expected to be activated by KDM6A trend in the expected direction in macrophages. Panel F adds pathway-level coherence with immune-related enrichments.

How to frame this responsibly: these are model-informed inferences that align with known biology and generate hypotheses, but they are not direct causal proof.

### Transition line
Figure 4 then extends this logic to cross-modality temporal dynamics.

---

## Slide 10 (2:30) - Figure 4 full view

### Script
Figure 4 asks whether Sunbear can infer missing ATAC dynamics from available RNA and sparse ATAC snapshots.

Panel A shows RNA and ATAC integration in latent space across overlapping time points. Panel B reports AUROC for predicting differential accessibility direction in held-out settings, with both RNA and ATAC query modes. Panel C looks at peak-wise AUROC across cells.

Then Panels D and E move from pure prediction to dynamics interpretation using time-lagged cross-correlation, TLCC. For each peak-gene pair, they shift one curve in time and measure lag-wise correlation.

This gives a rich lag profile rather than one static correlation value.

### Transition line
Now I’ll unpack what A-C establish first, then what D-E add biologically.

---

## Slide 11 (2:30) - Figure 4 deep interpretation

### Script
A-C establish technical validity. A suggests integration quality is reasonable. B shows temporal accessibility direction is often predicted above chance. C indicates the model captures substantial single-cell-level accessibility variation when ATAC is held out.

D-E then provide the dynamic claim: different peak-gene pairs have different lag structures. Some accessibility changes occur before nearby expression changes, consistent with chromatin priming. Others occur after, suggesting more complex regulation or feedback.

The important nuance is that the paper does not claim one universal lag. It shows a continuum of lags and both leading and trailing relationships.

This is a strength because it reflects realistic biology, but also a caution point because these lag estimates come from model-predicted trajectories and correlation structure, not direct perturbational temporal experiments.

### Transition line
With the figures covered, here is the balanced appraisal.

---

## Slide 12 (1:30) - Strengths and limits

### Script
Strengths: one integrated framework across time, condition, modality, and batch; scalable to very large data; and strong benchmarking against practical baselines.

Limits: no same-cell longitudinal ground truth, so all evaluation is proxy-based; TLCC-based timing interpretations are correlative; multimodal alignment currently benefits from coassay supervision; and smooth-transition assumptions may not hold for abrupt biology.

The right interpretation is that Sunbear is a high-quality integrative inference framework and hypothesis generator, especially where data collection is sparse or uneven.

### Transition line
I’ll close with the main takeaways in one minute.

---

## Slide 13 (1:30) - Conclusion

### Script
Sunbear demonstrates that a carefully factorized latent model can turn disconnected single-cell snapshots into coherent temporal and multimodal predictions.

In this paper, those predictions improve held-out reconstruction, recover known sex-linked biology, and expose candidate chromatin-expression timing programs.

The best next step is experimental follow-up on top-ranked predictions, especially in lineages with strong inferred sex-bias and in peak-gene pairs with strong lead-lag signals.

So the headline is: Sunbear does not replace experiments, but it dramatically improves where and how to aim them.

### Q&A opener
I’m happy to discuss baseline fairness, uncertainty reporting, and where this framework may fail under stronger temporal sparsity.

---

## Backup talking points (if asked)
- Why sinusoidal time encoding: continuous interpolation basis and expressive periodic components.
- Why adversarial time-invariance: improves disentanglement needed for counterfactual swapping.
- Why pseudobulk metrics: no true same-cell repeated measurement ground truth exists.
- Why Figure 4 is still useful despite correlative nature: it provides prioritized hypotheses for perturbation design.
