#!/usr/bin/env python3
"""
Generate Stent Optimization Pipeline Presentation (v3).
Style: Clean Professional (White/Black), VS Code-style Code Blocks, Deep Paper Integration.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

# ── Palette ──
BG_COLOR   = RGBColor(0xFF, 0xFF, 0xFF)
TEXT_MAIN  = RGBColor(0x00, 0x00, 0x00)
TEXT_DIM   = RGBColor(0x55, 0x55, 0x55)
VSCODE_BG  = RGBColor(0x1E, 0x1E, 0x1E) # Dark VS Code bg
ACCENT     = RGBColor(0x00, 0x7A, 0xCC) # VS Code blue

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)

# ── Helpers ──
def clean_layout(slide):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR

def add_title(slide, text, subtext=""):
    # Clean professional title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(12), Inches(1))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(32)
    p.font.color.rgb = TEXT_MAIN
    p.font.name = "Arial"
    p.font.bold = True
    
    if subtext:
        p2 = tf.add_paragraph()
        p2.text = subtext
        p2.font.size = Pt(18)
        p2.font.color.rgb = TEXT_DIM
        p2.space_before = Pt(4)

def add_text(slide, text, left=Inches(0.5), top=Inches(1.8), width=Inches(12), font_size=20):
    txBox = slide.shapes.add_textbox(left, top, width, Inches(5))
    tf = txBox.text_frame
    tf.word_wrap = True
    
    for line in text.strip().split('\n'):
        if not line.strip(): continue
        p = tf.add_paragraph()
        p.text = line.strip()
        p.font.size = Pt(font_size)
        p.font.color.rgb = TEXT_MAIN
        p.font.name = "Arial"
        p.space_before = Pt(8)

def add_code_vscode(slide, code, title="", left=Inches(0.5), top=Inches(1.8), width=Inches(6), height=Inches(5)):
    # Imitate a VS Code window
    # Valid "header" bar
    header = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Inches(0.3))
    header.fill.solid()
    header.fill.fore_color.rgb = RGBColor(0x33, 0x33, 0x33)
    header.line.fill.background()
    p = header.text_frame.paragraphs[0]
    p.text = f"  {title}" if title else "  code.py"
    p.font.size = Pt(10)
    p.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
    
    # Body
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top + Inches(0.3), width, height - Inches(0.3))
    box.fill.solid()
    box.fill.fore_color.rgb = VSCODE_BG
    box.line.fill.background()
    
    tf = box.text_frame
    tf.word_wrap = False # Code shouldn't wrap generally
    tf.margin_left = Pt(10)
    tf.margin_top = Pt(10)
    
    p = tf.paragraphs[0]
    p.text = code
    p.font.size = Pt(11) # Slightly larger for readability
    p.font.name = "Consolas"
    p.font.color.rgb = RGBColor(0xD4, 0xD4, 0xD4) # VS Code default text

def add_placeholder(slide, label, left, top, width, height):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xF0, 0xF0, 0xF0)
    shape.line.color.rgb = RGBColor(0x99, 0x99, 0x99)
    shape.line.dash_style = 1 # Solid
    
    tf = shape.text_frame
    p = tf.paragraphs[0]
    p.text = f"[ PASTE {label} HERE ]"
    p.font.size = Pt(14)
    p.font.color.rgb = TEXT_DIM
    p.alignment = PP_ALIGN.CENTER

# ══════════════════════════════════════════════════════════════════════
# SLIDE 1: Title
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)

tx = s.shapes.add_textbox(Inches(1.5), Inches(2.5), Inches(10), Inches(2))
p = tx.text_frame.paragraphs[0]
p.text = "Stent Optimization Pipeline"
p.font.size = Pt(44)
p.font.bold = True
p.font.color.rgb = TEXT_MAIN
p.alignment = PP_ALIGN.CENTER

p2 = tx.text_frame.add_paragraph()
p2.text = "Parametric Design • CFD • Bayesian Surrogate"
p2.font.size = Pt(20)
p2.font.color.rgb = TEXT_DIM
p2.alignment = PP_ALIGN.CENTER
p2.space_before = Pt(12)

# ══════════════════════════════════════════════════════════════════════
# SLIDE 2: Research Backing (The Paper)
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Validation: Maulik & Taira (2020)", "Phys. Rev. Fluids 5, 104401")

tx = s.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(12), Inches(1))
p = tx.text_frame.paragraphs[0]
p.text = "Key Finding: Fluid flow fields can be effectively modeled as probabilistic Gaussian distributions."
p.font.size = Pt(18)

add_placeholder(s, "FIGURE 1 FROM PAPER (PNN Architecture)", Inches(1), Inches(2.5), Inches(5), Inches(4))
add_placeholder(s, "EQ 2 FROM PAPER (Gaussian Output)", Inches(7), Inches(2.5), Inches(5), Inches(4))

# ══════════════════════════════════════════════════════════════════════
# SLIDE 3: Why This Approach?
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Methodology: Data-Efficient Learning")

tx = s.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(5.5), Inches(5))
tf = tx.text_frame
p = tf.paragraphs[0]
p.text = "The Paper's PNN vs. My GP Approach"
p.font.bold = True
p.font.size = Pt(18)

items = [
    "Maulik & Taira use Probabilistic NNs",
    "→ Requires 1000s of snapshots (High Data)",
    "",
    "I use Gaussian Processes (Kriging)",
    "→ Works with <200 snapshots (Low Data)",
    "→ COMSOL is expensive (hours/run)",
    "",
    "Result: Same physical validity (Gaussian assumption), but feasible for my compute budget."
]
for item in items:
    p = tf.add_paragraph()
    p.text = item
    p.font.size = Pt(16)
    p.space_before = Pt(8)

add_placeholder(s, "FIGURE showing uncertainty bounds (shaded)", Inches(6.5), Inches(1.8), Inches(6), Inches(4.5))

# ══════════════════════════════════════════════════════════════════════
# SLIDE 4: The 5-Step Pipeline
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Pipeline Overview")

steps = [
    ("1. CAD", "Parametric Geometry"),
    ("2. Sampling", "LHS Space-Filling"),
    ("3. Simulation", "COMSOL CFD"),
    ("4. Surrogate", "Gaussian Process"),
    ("5. Optimization", "Bayesian Loop")
]

for i, (head, sub) in enumerate(steps):
    left = Inches(0.8) + i * Inches(2.4)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, Inches(3), Inches(2.2), Inches(1.5))
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xFA, 0xFA, 0xFA)
    box.line.color.rgb = TEXT_MAIN
    
    p = box.text_frame.paragraphs[0]
    p.text = head
    p.font.bold = True
    p.font.color.rgb = TEXT_MAIN
    p.alignment = PP_ALIGN.CENTER
    
    p2 = box.text_frame.add_paragraph()
    p2.text = sub
    p2.font.size = Pt(12)
    p2.font.color.rgb = TEXT_DIM
    p2.alignment = PP_ALIGN.CENTER


# ══════════════════════════════════════════════════════════════════════
# SLIDE 5: Step 1 - CAD
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "1. Parametric CAD Generation")

code = """@dataclass
class StentParameters:
    stent_french: float = 6.0
    # Ratios guarantee feasibility [0-1]
    r_t: float = 0.15   # Wall thickness
    r_sh: float = 0.5   # Side hole dia
    
    def validate(self):
        if self.ID < 0.6: raise ValueError
        
gen = StentGenerator(params)
gen.export_step("design.step")"""

add_code_vscode(s, code, "src/cad/stent_generator.py", left=Inches(0.5), width=Inches(7))

tx = s.shapes.add_textbox(Inches(8), Inches(2), Inches(5), Inches(4))
p = tx.text_frame.paragraphs[0]
p.text = "Features:"
p.font.bold = True
p = tx.text_frame.add_paragraph()
p.text = "• 16 Design Parameters\n• Build123d geometry kernel\n• Automatic constraint validation"

# ══════════════════════════════════════════════════════════════════════
# SLIDE 6: Step 2 - Sampling
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "2. LHS Sampling")

code = """from scipy.stats import qmc

# Latin Hypercube Sampling
sampler = qmc.LatinHypercube(d=16)
samples = sampler.random(n=180)

# Feasibility Filter
valid_designs = []
for s in samples:
   if check_constraints(s):
       valid_designs.append(s)
       
# Result: ~60 valid designs for simulation"""

add_code_vscode(s, code, "src/sampling/lhs_generator.py", left=Inches(0.5), width=Inches(7))
add_placeholder(s, "SCATTER PLOT OF SAMPLES", Inches(8), Inches(2), Inches(4.5), Inches(4))

# ══════════════════════════════════════════════════════════════════════
# SLIDE 7: Step 3 - CFD
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "3. CFD Simulation (COMSOL)")

add_placeholder(s, "SCREENSHOT OF COMSOL MESH / VELOCITY FIELD", Inches(1), Inches(1.8), Inches(11), Inches(5))

# ══════════════════════════════════════════════════════════════════════
# SLIDE 8: Step 4 - Surrogate
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "4. Gaussian Process Surrogate")

code = """class GPModel:
    def fit(self, X, y):
        # Matérn 5/2 kernel (Standard for Fluids)
        # ARD (Automatic Relevance Determination)
        covar = ScaleKernel(
            MaternKernel(nu=2.5, ard_num_dims=16)
        )
        self.model = SingleTaskGP(X, y, covar)

    def predict(self, X):
        # Returns Mean AND Variance
        return model.posterior(X)"""

add_code_vscode(s, code, "src/surrogate/gp_model.py", left=Inches(0.5), width=Inches(7))

tx = s.shapes.add_textbox(Inches(8), Inches(2), Inches(4.5), Inches(4))
p = tx.text_frame.paragraphs[0]
p.text = "Why Matérn 5/2?"
p.font.bold = True
p = tx.text_frame.add_paragraph()
p.text = "Matches the smoothness properties of fluid flow (infinite smoothness of RBF is unrealistic for turbulence/transitions)."


# ══════════════════════════════════════════════════════════════════════
# SLIDE 9: Step 5 - Optimization
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "5. Bayesian Optimization")

# Equations
tx = s.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(12), Inches(2))
p = tx.text_frame.paragraphs[0]
p.text = "Objectives:"
p.font.bold = True
p.font.size = Pt(16)

# Unicode math approximations
lines = [
    "Minimize Pressure Drop:   min ΔP(x)",
    "Maximize Total Flow:      max Q_total(x)",
    "Minimize Uniformity Coeff: min CV(Q_sh)"
]
for line in lines:
    p = tx.text_frame.add_paragraph()
    p.text = f"  {line}"
    p.font.size = Pt(20)
    p.font.name = "Arial"
    p.space_before = Pt(8)

code = """# Acquisition Function: Expected Improvement
# Balances Exploitation (Best Mean) & Exploration (High Var)

acq = qExpectedImprovement(
    model=gp_model,
    best_f=best_observed_y
)

candidates, _ = optimize_acqf(acq, q=5)"""

add_code_vscode(s, code, "src/optimization/optimizer.py", left=Inches(0.5), top=Inches(4), width=Inches(7), height=Inches(3))



# ══════════════════════════════════════════════════════════════════════
# SLIDE 10: Verification (NEW)
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Verification: We Don't Trust Black Boxes")

tx = s.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(5.5), Inches(4))
p = tx.text_frame.paragraphs[0]
p.text = "How do we know the optimizer works?"
p.font.bold = True
p.font.size = Pt(18)

p = tx.text_frame.add_paragraph()
p.text = "We wrote specific tests to prove it verifies constraints:"
p.font.size = Pt(16)
p.space_before = Pt(12)

items = [
    "• test_suggest_valid_candidates",
    "  → Proves BO output is within bounds",
    "",
    "• test_constraints_are_respected",
    "  → Proves impossible designs are rejected"
]
for item in items:
    p = tx.text_frame.add_paragraph()
    p.text = item
    p.font.size = Pt(16)
    p.space_before = Pt(6)

code = """def test_suggest_valid_candidates(self):
    candidates = opt.suggest(n=5)
    
    # Assert all suggested designs are valid
    for col in candidates.columns:
        assert candidates[col].min() >= bounds[0]
        assert candidates[col].max() <= bounds[1]
        
    # Assert geometry is physically possible
    assert check_feasibility(candidates).all()"""

add_code_vscode(s, code, "src/optimization/tests/test_optimizer.py", left=Inches(6.5), width=Inches(6.5), height=Inches(4.5))


# ══════════════════════════════════════════════════════════════════════
# SLIDE 11: Orchestration
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Full Campaign Loop")

code = """# run_campaign.py
def main():
    while not converged:
        1. Load Results (CSV)
        2. Train GP Surrogate (X, y)
        3. Optimize Acquisition -> New Candidates
        4. Generate CAD
        5. Run COMSOL Batch
        
# Automation allows running overnight."""

add_code_vscode(s, code, "scripts/run_optimization_campaign.py", left=Inches(1.5), width=Inches(10), height=Inches(4.5))

# ══════════════════════════════════════════════════════════════════════
# SLIDE 12: Summary
# ══════════════════════════════════════════════════════════════════════
s = prs.slides.add_slide(prs.slide_layouts[6])
clean_layout(s)
add_title(s, "Summary")

add_text(s, 
    "1. Validated by Taira (2020): Gaussian assumption holds for fluids.\n"
    "2. Data-Efficient: GP surrogate replaces 1000s of simulations.\n"
    "3. Automated: End-to-end Python pipeline (CAD → CFD → AI).\n"
    "4. Optimized: Finds the best stent geometry without human guessing.",
    width=Inches(8))

# ── Save ──
out_path = os.path.join(os.path.dirname(__file__), "..", "admin", "stent_pipeline_v4.pptx")
prs.save(out_path)
print(f"Saved to {out_path}")
