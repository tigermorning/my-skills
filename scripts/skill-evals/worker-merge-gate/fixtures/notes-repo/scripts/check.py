"""All checks for this repo: the unit tests. Run from the repo root: python scripts/check.py"""
import subprocess
import sys

sys.exit(subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"]).returncode)
