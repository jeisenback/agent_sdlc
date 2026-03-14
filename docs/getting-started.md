# Getting Started

1. Bootstrap the repository (creates a venv, installs dev deps, and runs tests):

```bash
python scripts/bootstrap.py
```

2. Run tests directly (after activating a venv):

```bash
pytest -q
```

3. Run generator to scaffold a new project:

```bash
python scripts/init_project.py --name myproj --package myproj_pkg --out ../myproj
```
