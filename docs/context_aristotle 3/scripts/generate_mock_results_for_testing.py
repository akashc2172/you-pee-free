#!/usr/bin/env python3
"""Generate mock results.csv and flux summary for testing the merge script."""

import argparse
import pandas as pd
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", default="campaign_test")
    args = parser.parse_args()

    base_dir = Path("data/campaigns") / args.campaign
    base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create mock results.csv (legacy)
    results_data = [
        {"design_id": "design_0000", "run_status": "valid", "legacy_metric": 1.0, "deltaP_Pa": 490.0},
        {"design_id": "design_0001", "run_status": "valid", "legacy_metric": 2.2, "deltaP_Pa": 490.0},
        {"design_id": "design_0002", "run_status": "failed", "legacy_metric": 0.0, "deltaP_Pa": 0.0},
    ]
    pd.DataFrame(results_data).to_csv(base_dir / "results.csv", index=False)

    # 2. Create mock flux summary
    flux_data = [
        {"design_id": "design_0000", "p_ramp": 1, "deltaP_Pa": 490.5, "Q_out_ml_min": 10.5, "exchange_number": 0.15},
        {"design_id": "design_0001", "p_ramp": 1, "deltaP_Pa": 491.0, "Q_out_ml_min": 11.2, "exchange_number": 0.18, "hole_flux_centroid_norm": 0.5},
    ]
    pd.DataFrame(flux_data).to_csv(base_dir / "campaign_flux_summary.csv", index=False)

    print(f"Generated mock data in {base_dir}")

if __name__ == "__main__":
    main()
