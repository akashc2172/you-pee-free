---
name: Run Optimization Campaign
description: Instructions for running the stent optimization active learning loop.
---

# Run Optimization Campaign

## Overview
This skill executes the Bayesian Optimization loop to discover optimal stent designs.

## Prerequisites
- Python 3.8+
- Dependencies installed (`make install`)
- COMSOL Multiphysics (optional, for FEM evaluation)

## Usage

### Via CLI
```bash
python3 src/cli.py run-campaign --campaign <CAMPAIGN_NAME> --batch_size <N>
```

### Via Makefile
```bash
make run-campaign
```
*Defaults to `campaign_001` with batch size 5.*

## options
- `--campaign`: Name of the campaign (creates folder in `data/campaigns/`).
- `--batch_size`: Number of new candidates to generate per iteration.
- `--init_lhs`: Initialize with Latin Hypercube Sampling (first run only).
- `--n_init`: Number of initial LHS samples (default: 20).

## Output
- `data/campaigns/<CAMPAIGN>/results.csv`: Log of all tested designs.
- `data/campaigns/<CAMPAIGN>/cad/`: Generated geometry files.
- `logs/campaign.log`: Execution logs.

## Troubleshooting
- **"No data found"**: Run with `--init_lhs` for the first iteration.
- **"COMSOL not found"**: Ensure COMSOL is in your PATH or skipped if using surrogate only.
