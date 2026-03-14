import subprocess
import sys
from pathlib import Path


def test_init_project_creates_pyproject(tmp_path):
    out = tmp_path
    project_name = "demo_proj"
    package_name = "demo_pkg"

    cmd = [sys.executable, "scripts/init_project.py", "--name", project_name, "--package", package_name, "--out", str(out)]
    res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if res.returncode != 0:
        raise AssertionError(f"init_project failed: {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")

    project_dir = out / project_name
    assert project_dir.exists()
    pyproject = project_dir / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text(encoding="utf8")
    assert project_name in content
