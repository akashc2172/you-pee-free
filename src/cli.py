#!/usr/bin/env python3
"""
Unified CLI for Stent Optimization Project
"""
import argparse
import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a shell command and stream output."""
    print(f"🚀 Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)

def run_campaign(args):
    """Run the optimization campaign."""
    cmd = [
        sys.executable, 
        "scripts/run_optimization_campaign.py",
        "--campaign", args.campaign,
        "--batch_size", str(args.batch_size)
    ]
    if args.init_lhs:
        cmd.append("--init_lhs")
        cmd.extend(["--n_init", str(args.n_init)])
    
    run_command(cmd)

def run_comsol_campaign(args):
    """Run COMSOL batch solves for a generated campaign manifest."""
    cmd = [
        sys.executable,
        "scripts/run_comsol_campaign.py",
        "--campaign", args.campaign,
        "--base_mph", args.base_mph,
        "--comsol_exec", args.comsol_exec,
    ]
    if args.batch_file:
        cmd.extend(["--batch_file", args.batch_file])
    if args.output_dir:
        cmd.extend(["--output_dir", args.output_dir])
    if args.results_file:
        cmd.extend(["--results_file", args.results_file])
    if args.no_resume:
        cmd.append("--no_resume")

    run_command(cmd)

def debug_comsol_smoke(args):
    """Run one COMSOL smoke attempt with verbose compatibility reporting."""
    cmd = [
        sys.executable,
        "scripts/debug_comsol_smoke_run.py",
        "--base_mph", args.base_mph,
        "--cad_file", args.cad_file,
        "--output_dir", args.output_dir,
        "--comsol_exec", args.comsol_exec,
    ]
    if args.design_id:
        cmd.extend(["--design_id", args.design_id])
    run_command(cmd)

def generate_presentation(args):
    """Generate the project presentation."""
    # Check if script exists, if not, warn user (or help them find it)
    script_path = Path("scripts/generate_presentation.py")
    if not script_path.exists():
        print(f"❌ Error: {script_path} not found. Please restore it first.")
        sys.exit(1)
        
    cmd = [sys.executable, str(script_path)]
    if args.output:
        cmd.extend(["--output", args.output])
    
    run_command(cmd)

def check_env(args):
    """Verify the environment."""
    cmd = [sys.executable, "scripts/check_env.py"]
    run_command(cmd)

def run_tests(args):
    """Run the test suite."""
    cmd = [sys.executable, "-m", "pytest"]
    if args.target:
        cmd.append(args.target)
    else:
        cmd.append("src") # Default to all checks
    
    run_command(cmd)

def main():
    parser = argparse.ArgumentParser(description="Stent Optimization CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    subparsers.required = True

    # run-campaign
    campaign_parser = subparsers.add_parser("run-campaign", help="Run optimization loop")
    campaign_parser.add_argument("--campaign", default="campaign_001", help="Campaign ID")
    campaign_parser.add_argument("--batch_size", type=int, default=5, help="Batch size")
    campaign_parser.add_argument("--init_lhs", action="store_true", help="Init with LHS")
    campaign_parser.add_argument("--n_init", type=int, default=20, help="LHS samples")
    campaign_parser.set_defaults(func=run_campaign)

    # run-comsol-campaign
    comsol_parser = subparsers.add_parser("run-comsol-campaign", help="Run COMSOL batch for a campaign")
    comsol_parser.add_argument("--campaign", required=True, help="Campaign ID")
    comsol_parser.add_argument("--base_mph", required=True, help="Base COMSOL MPH template")
    comsol_parser.add_argument("--comsol_exec", default="comsol", help="COMSOL executable path")
    comsol_parser.add_argument("--batch_file", help="Explicit batch CSV path")
    comsol_parser.add_argument("--output_dir", help="Run output directory")
    comsol_parser.add_argument("--results_file", help="Aggregate results.csv path")
    comsol_parser.add_argument("--no_resume", action="store_true", help="Disable checkpoint resume")
    comsol_parser.set_defaults(func=run_comsol_campaign)

    debug_parser = subparsers.add_parser(
        "debug-comsol-smoke",
        help="Run one COMSOL smoke attempt with a compatibility report",
    )
    debug_parser.add_argument("--base_mph", required=True, help="Base COMSOL MPH template")
    debug_parser.add_argument("--cad_file", required=True, help="Path to one STEP file")
    debug_parser.add_argument("--output_dir", required=True, help="Output directory for the smoke run")
    debug_parser.add_argument("--design_id", help="Optional design ID override")
    debug_parser.add_argument("--comsol_exec", default="comsol", help="COMSOL executable path")
    debug_parser.set_defaults(func=debug_comsol_smoke)

    # generate-presentation
    pres_parser = subparsers.add_parser("generate-presentation", help="Generate PPTX slides")
    pres_parser.add_argument("--output", help="Output filename")
    pres_parser.set_defaults(func=generate_presentation)

    # check-env
    check_parser = subparsers.add_parser("check-env", help="Verify environment")
    check_parser.set_defaults(func=check_env)

    # test
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("target", nargs="?", help="Specific test file or dir")
    test_parser.set_defaults(func=run_tests)

    args = parser.parse_args()
    
    # Execute the selected function
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
