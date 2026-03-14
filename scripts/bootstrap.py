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

    pip = str(venv_dir / "Scripts" / "pip") if (venv_dir / "Scripts").exists() else str(venv_dir / "bin" / "pip")

    run([pip, "install", "--upgrade", "pip"])
    if (ROOT / "requirements.txt").exists():
        run([pip, "install", "-r", "requirements.txt"])
    if (ROOT / "requirements-dev.txt").exists():
        run([pip, "install", "-r", "requirements-dev.txt"])

    # install pre-commit hooks
    run([pip, "install", "pre-commit"])
    run([str(venv_dir / "Scripts" / "pre-commit") if (venv_dir / "Scripts").exists() else str(venv_dir / "bin" / "pre-commit"), "install"])  # type: ignore[arg-type]

    # Run the test suite
    run([str(venv_dir / "Scripts" / "python") if (venv_dir / "Scripts").exists() else str(venv_dir / "bin" / "python"), "-m", "pytest", "-q"])


if __name__ == "__main__":
    main()
