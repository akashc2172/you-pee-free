# Stent Optimization Pipeline

A comprehensive Python platform for optimizing pediatric ureteral stent designs through parametric CAD generation, COMSOL CFD simulation, Gaussian Process surrogate modeling, and Bayesian multi-objective optimization.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -e ".[all]"

# Generate a test stent
python -c "
from src.cad import StentGenerator, StentParameters

params = StentParameters(stent_french=6.0, n_mid=5)
gen = StentGenerator(params)
gen.export_step('data/cad_exports/test_stent.step')
print(gen.get_info())
"
```

## 📂 Project Structure

```
masters/
├── admin/              # Proposals, presentations, tracker
├── config/             # Parameter definitions (parameters.yaml)
├── data/               # Generated data
│   ├── lhs_batches/    # LHS samples (CSV)
│   ├── cad_exports/    # .step files
│   ├── comsol_results/ # COMSOL outputs
│   └── surrogate_models/
├── docs/               # Technical documentation
├── references/         # Literature (PDFs, papers)
├── src/                # Core code
│   ├── cad/            # CAD generation (build123d)
│   ├── sampling/       # LHS + feasibility filtering
│   ├── comsol/         # COMSOL automation
│   ├── surrogate/      # GP training & validation
│   └── optimization/   # BO loop
├── scripts/            # CLI entry points
├── notebooks/          # Exploratory analysis
└── tests/              # Integration tests
```

## 🔧 CAD Generation

The `StentGenerator` creates parametric stent geometries with:
- Proximal/distal helical coils (independent parameters)
- Hollow tube body with configurable wall thickness
- Side holes in proximal, middle, distal sections
- Unroofed (half-pipe) distal section option
- Full validation of geometric constraints

```python
from src.cad import StentGenerator, StentParameters

# Fraction-based parameters guarantee valid geometry
params = StentParameters(
    stent_french=7.0,       # French size (1 Fr = 0.333 mm)
    stent_length=200,       # Body length (mm)
    r_t=0.15,               # Wall thickness = 15% of OD
    r_sh=0.5,               # Side hole = 50% of ID
    n_prox=3, n_mid=8, n_dist=3,
    unroofed_length=15.0    # Half-pipe distal cut
)

gen = StentGenerator(params)
gen.export_step("output.step")  # For COMSOL import
```

## 🧪 Running Tests

```bash
pytest src/ -v
```

## 📋 Documentation

- [Parameter Schema](docs/parameter_schema.md)
- [Metrics Catalog](docs/metrics_catalog.md)
- [Pipeline Overview](docs/pipeline_overview.md)
- [GP/BO Decisions](docs/decisions_gp_surrogate.md)

## 📚 References

- [Maulik & Taira (2020) Analysis](docs/taira_paper_analysis.md)
