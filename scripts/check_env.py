#!/usr/bin/env python3
"""
Environment Verification Script
Checks if the necessary dependencies and directory structures exist.
"""
import sys
import shutil
from pathlib import Path
import importlib.util

def check_python_version():
    """Verify Python 3.8+"""
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 8):
        print(f"❌ Python version {sys.version.split()[0]} is too old. Need 3.8+")
        return False
    print(f"✅ Python {sys.version.split()[0]}")
    return True

def check_package(package_name):
    """Check if a python package is installed."""
    if importlib.util.find_spec(package_name) is None:
        print(f"❌ Missing package: {package_name}")
        return False
    print(f"✅ Package found: {package_name}")
    return True

def check_command(cmd, name=None):
    """Check if a shell command exists."""
    name = name or cmd
    if shutil.which(cmd) is None:
        print(f"⚠️  Command not found: {name} (Optional but recommended)")
        return False
    print(f"✅ Command found: {name}")
    return True

def check_dir(path):
    """Check if a directory exists, create if not."""
    p = Path(path)
    if not p.exists():
        print(f"⚠️  Directory missing: {path} (Creating...)")
        p.mkdir(parents=True, exist_ok=True)
        return True
    print(f"✅ Directory exists: {path}")
    return True

def main():
    print("=== Environment Verification ===")
    
    # 1. Python Environment
    all_good = check_python_version()
    
    # Core dependencies from pyproject.toml / requirements
    packages = [
        "numpy", 
        "pandas", 
        "torch", 
        "gpytorch", 
        "botorch", 
        "scipy",
        "matplotlib",
        "pptx" # python-pptx
    ]
    
    for pkg in packages:
        if not check_package(pkg):
            all_good = False

    # 2. External Tools
    check_command("git")
    check_command("comsol", "COMSOL Multiphysics") # Likely not in path, but good to check

    # 3. Project Structure
    project_root = Path(__file__).parent.parent
    dirs = [
        "data",
        "data/campaigns",
        "admin",
        "logs",
        "src/cad",
        "src/optimization",
        "src/surrogate"
    ]
    
    for d in dirs:
        check_dir(project_root / d)

    print("\n=== Summary ===")
    if all_good:
        print("✅ Environment looks good!")
        sys.exit(0)
    else:
        print("❌ Some checks failed. Please install missing dependencies.")
        sys.exit(1)

if __name__ == "__main__":
    main()
