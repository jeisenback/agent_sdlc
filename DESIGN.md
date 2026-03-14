# agent_sdlc — Design Document

## Overview
`agent_sdlc` provides reusable building blocks for agent-assisted SDLC workflows: LLM provider abstractions, retry utilities, database adapters, and pluggable agents (ingestion, feature-generation, evaluation). The package is designed so teams can run fast unit tests offline and swap in production adapters.

## Goals
- Extract core primitives (LLM wrapper, retry, db factory) behind clear interfaces.
- Provide a `ProviderProtocol` and a `DummyLLMProvider` to allow deterministic unit tests without external APIs.
- Offer DB adapters with a lightweight sqlite fallback and a `SqlAlchemyAdapter` for production.
- Keep CI fast by running unit tests with dummy providers and gated integration runs (Docker/testcontainers) for heavy dependencies.

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
