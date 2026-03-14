
# agent_sdlc

Lightweight package of agent-assisted SDLC primitives: provider abstractions, retry utilities, DB adapters, and small example agents.

![CI](https://github.com/jeisenback/agent_sdlc/actions/workflows/ci.yml/badge.svg)

Quickstart

1) Bootstrap the repository (creates a venv, installs dev deps, and runs tests):

```bash
python scripts/bootstrap.py
```

2) Run tests directly (after activating a venv):

```bash
pytest -q
```

Running integration tests

Integration tests are skipped by default. To run them locally set the `RUN_INTEGRATION` environment variable and install integration deps (SQLAlchemy):

```bash
python -m pip install sqlalchemy
export RUN_INTEGRATION=1   # Linux/macOS
setx RUN_INTEGRATION 1     # Windows (PowerShell)
pytest -q tests/integration
```

Why this repo

This project is designed to be a reusable template for AI-assisted SDLC workflows. It provides deterministic test primitives (`DummyLLMProvider`, `SqliteAdapter`) so CI can run fast without external APIs, and small agents you can extend.

Provider and adapters

- For tests and local development use `agent_sdlc.core.providers.DummyLLMProvider`.
- This repository includes non-networking stubs for `OpenAIProvider` and `AnthropicProvider` in `agent_sdlc.core.providers` — replace them with concrete implementations that call SDKs in production.

Project generator & bootstrapping

The repo is intended to act as a template. Use `scripts/bootstrap.py` to set up a local development environment and `scripts/init_project.py` to scaffold a new project from this template.

CI

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs unit tests and a minimal lint check on PRs. Integration tests run in the scheduled/manual workflow (`.github/workflows/integration.yml`).

Contributing

See `CONTRIBUTING.md` for developer setup, code style, and PR guidance.
