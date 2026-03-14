# agent_sdlc

Lightweight package of agent-assisted SDLC primitives: provider abstractions, retry utilities, DB adapters, and small example agents.

Quickstart

1) Bootstrap the repository (creates a venv, installs dev deps, and runs tests):

```bash
python scripts/bootstrap.py
```

2) Run tests directly (after activating a venv):

```bash
pytest -q
```

Why this repo

This project is designed to be a reusable template for AI-assisted SDLC workflows. It provides deterministic test primitives (`DummyLLMProvider`, `SqliteAdapter`) so CI can run fast without external APIs, and small agents you can extend.

Provider and adapters

- For tests and local development use `agent_sdlc.core.providers.DummyLLMProvider`.
- This repository includes non-networking stubs for `OpenAIProvider` and `AnthropicProvider` in `agent_sdlc.core.providers` — replace them with concrete implementations that call SDKs in production.

Project generator & bootstrapping

The repo is intended to act as a template. A future `scripts/init_project.py` generator can scaffold new projects from this template (CI, README, package name). For now, use `scripts/bootstrap.py` to set up a local development environment.

CI

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs unit tests and a minimal lint check on PRs. Add CI badges here once the main workflow is enabled.

Contributing

See `CONTRIBUTING.md` for developer setup, code style, and PR guidance.
