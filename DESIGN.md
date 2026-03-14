# agent_sdlc — Design Document

## Overview
`agent_sdlc` provides reusable building blocks for agent-assisted SDLC workflows: LLM provider abstractions, retry utilities, database adapters, and pluggable agents (ingestion, feature-generation, evaluation). The package is designed so teams can run fast unit tests offline and swap in production adapters.

## Goals
- Extract core primitives (LLM wrapper, retry, db factory) behind clear interfaces.
- Provide a `ProviderProtocol` and a `DummyLLMProvider` to allow deterministic unit tests without external APIs.
- Offer DB adapters with a lightweight sqlite fallback and a `SqlAlchemyAdapter` for production.
- Keep CI fast by running unit tests with dummy providers and gated integration runs (Docker/testcontainers) for heavy dependencies.

## AI-assisted workflow

- Human role: provide direction, prioritise work, and make high-level architecture or security decisions.
- AI role: implement, test, refactor, and maintain routine code changes (agents, adapters, CI), using injected providers and adapters.
- Automation: CI (GitHub Actions) runs tests and linters; agents can open PRs, run local demos, and update docs automatically.

The project is structured so that AI tools (Copilot, Claude, or other agents) can perform most implementation tasks given human oversight.

## Non-goals
- Not publishing opinionated orchestration or runtime environments. This package focuses on primitives and adapters.

## High-level Architecture
- `agent_sdlc.core` — low-level utilities (retry, logging, types, db adapter interfaces)
- `agent_sdlc.core.llm` — provider protocol and concrete providers
- `agent_sdlc.agents` — pluggable agents that accept provider & adapter injections
- `agent_sdlc.adapters` — DB adapters (sqlite, sqlalchemy), optional external adapters
- `agent_sdlc.examples` — example scripts (backtest, pipelines)

## Public API (proposed)
- `ProviderProtocol` — send/receive interface for LLMs
- `DummyLLMProvider` — deterministic, local responses for tests
- `with_retry` decorator — standardized retry policy
- `DBAdapter` / `SqlAlchemyAdapter` / `SqliteAdapter` — DB abstraction layer
- `agents.*` — functions/classes that accept `provider: ProviderProtocol` and `db_adapter: DBAdapter`

## CI Strategy
- Unit tests: run with `DummyLLMProvider` + `SqliteAdapter` (fast). Execute on PRs.
- Integration tests: use `testcontainers.postgres` + real providers (optional API keys). Run only on main/nightly or gated workflows.

- Continuous workflow: GitHub Actions runs tests + minimal lint on PRs. A nightly workflow can run heavier integration tests.

Compatibility note: pinning `pydantic` to `<2` keeps a stable API surface for generated code and tests; a migration plan will be scheduled to adopt Pydantic v2 features.

## Template & Bootstrapping

- The repository will act as a project template. A generator (`scripts/init_project.py`) or a `scripts/bootstrap` script should create a new project from this template, producing:
	- `pyproject.toml` / `requirements.txt` adjusted for the new package name
	- `.github/workflows/ci.yml` minimal CI for unit tests
	- `README.md` with quickstart and bootstrap instructions
	- example agents and runner scripts

- The bootstrap experience should be documented in `CONTRIBUTING.md` and should include a one-command developer setup (venv creation, install dev deps, run tests).

## Developer experience

- Devs should be able to run `pytest -q` locally after following `scripts/bootstrap`.
- Provide `pre-commit` configuration and recommended formatter/linter settings so generated projects have consistent style.
- Keep runtime optional dependencies out of the fast PR path; split `requirements-dev.txt` and `requirements.txt` so CI can install minimal deps for unit tests.

## Migration Plan (brief)
1. Create package skeleton and tests (this step).
2. Extract deterministic utilities (retry, types) and LLM abstractions.
3. Refactor one agent to accept adapters; add tests.
4. Sweep repository imports and add compatibility shims.

## Security & Secrets
- Providers requiring API keys must be injected at runtime via env vars or secret managers. The package never stores secrets in code or tests.

## Future work
- Add typed response schemas with Pydantic models for agent outputs.
- Provide optional async ProviderProtocol variant.
