# Contributing to agent_sdlc

Thanks for contributing! This project is designed to be AI-assisted and easy to
bootstrap. This document explains how to set up the dev environment, run tests,
and submit PRs.

Developer setup

1. Bootstrap the project (creates `.venv`, installs dev deps, installs pre-commit hooks, and runs tests):

```bash
python scripts/bootstrap.py
```

2. Activate the venv (if you prefer manual steps):

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

3. Run tests:

```bash
pytest -q
```

Code style

- We use `black`, `isort`, and `ruff` via `pre-commit`. Hooks are configured in `.pre-commit-config.yaml`.
- Run `pre-commit run --all-files` to check formatting locally.

Provider adapters

- Use `DummyLLMProvider` for deterministic tests. Replace the stub classes in
  `agent_sdlc/core/providers.py` with concrete implementations when integrating
  a real provider. Never commit API keys; use environment variables and GitHub
  Secrets for CI.

Pull request workflow

- Create a feature branch off `main`.
- Add tests for new behavior; CI runs unit tests on PRs.
- Keep PRs small and focused; include a short description of the change and any
  migration or compatibility notes.

Security

- Do not add secrets to code or tests. Use environment variables and document any
  required keys in `.env.example` (do not add the `.env` file to the repo).

Questions

If you're unsure about architecture or public API changes, open an issue first
so we can discuss design before implementation.
