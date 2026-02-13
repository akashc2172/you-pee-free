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
