"""Bootstrap helper: create venv, install dev deps, and run tests.

Usage: python scripts/bootstrap.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        run([sys.executable, "-m", "venv", str(venv_dir)])

    # Prefer calling the venv Python and using "-m pip" to avoid pip-binary issues
    venv_python = str(venv_dir / "Scripts" / "python") if (venv_dir / "Scripts").exists() else str(venv_dir / "bin" / "python")

    run([venv_python, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    if (ROOT / "requirements.txt").exists():
        run([venv_python, "-m", "pip", "install", "-r", "requirements.txt"])
    if (ROOT / "requirements-dev.txt").exists():
        run([venv_python, "-m", "pip", "install", "-r", "requirements-dev.txt"])

    # install pre-commit hooks (via the venv Python)
    run([venv_python, "-m", "pip", "install", "pre-commit"])
    run([venv_python, "-m", "pre_commit", "install"])

    # Run the test suite via the venv Python
    run([venv_python, "-m", "pytest", "-q"])


if __name__ == "__main__":
    main()
