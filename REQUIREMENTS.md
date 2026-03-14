# agent_sdlc — Requirements

## Purpose
This document captures the functional and non-functional requirements for the `agent_sdlc` package: a set of reusable primitives for building agent-assisted software development lifecycles (LLM provider abstractions, retry utilities, DB adapters, and pluggable agents).

---

## Functional Requirements

- FR1: Provider Abstraction — Expose a clear `ProviderProtocol` that standardizes request/response semantics for LLM providers.
- FR2: Dummy Provider — Provide a `DummyLLMProvider` for deterministic, offline unit tests supporting configurable canned responses and latency simulation.
- FR3: Retry Utility — Provide a reusable `with_retry` decorator and configuration for common retry patterns (exponential backoff, max attempts, jitter).
- FR4: DB Adapter Interface — Define a `DBAdapter` interface to abstract persistence operations (connect, execute, fetch, transactional context) so agents can operate against multiple backends.
- FR5: Sqlite Adapter — Include a lightweight, zero-dependency sqlite adapter suitable for fast unit tests.
- FR6: SqlAlchemy Adapter — Provide a `SqlAlchemyAdapter` that implements `DBAdapter` for production systems using SQLAlchemy engines.
- FR7: Agent Contracts — Design agent entry points (ingestion, feature generation, evaluation) that accept `provider: ProviderProtocol` and `db_adapter: DBAdapter` as explicit dependencies.
- FR8: Example Consumers — Ship at least two example scripts: a GDELT→volatility backtest and a simple ingestion pipeline demonstrating adapter injection.
- FR9: Tests — Provide unit tests exercising core APIs using `DummyLLMProvider` and `SqliteAdapter`.
- FR10: Configurable Logging — Provide structured logging helpers and allow agents to opt-in to context-enriched logs.

---

## Non-Functional Requirements

- NFR1: Testability — Unit tests must run offline without network access and complete quickly (target: < 30s for core unit suite).
- NFR2: Modularity — Components must have low coupling and clear interfaces so they can be adopted independently.
- NFR3: Fast CI — PR-level CI should run only unit tests that use `DummyLLMProvider` + `SqliteAdapter`; heavy integration tests are gated to main/nightly.
- NFR4: Security — The package must never store provider secrets in code or test fixtures; secrets are injected at runtime via env vars or secret stores.
- NFR5: Performance — Production adapters (e.g., `SqlAlchemyAdapter`) should not introduce undue overhead; reasonable defaults and connection pooling should be supported.
- NFR6: Reliability — Retry utility must be robust and configurable; default policies should handle common transient failures.
- NFR7: Observability — Provide hooks for tracing and metrics (optional integration points) so callers can attach instrumentation.
- NFR8: Compatibility — Support Python 3.10+. Avoid using language features that break 3.10 compatibility.
- NFR9: Extensibility — New provider/adapters should be pluggable without modifying core package code.
- NFR10: Maintainability — Keep public API surface small and documented; use type hints and Pydantic models for external-facing schemas.

---

## Acceptance Criteria

- AC1: A `ProviderProtocol` and `DummyLLMProvider` exist and are covered by unit tests.
- AC2: `DBAdapter` interface exists with at least `SqliteAdapter` and `SqlAlchemyAdapter` implementations and tests for both (sqlite unit tests run in PR CI).
- AC3: One agent (e.g., `feature_generation`) refactored to accept injected `provider` and `db_adapter`, with unit tests demonstrating swapability.
- AC4: Examples included: `examples/backtest_gdelt_vol.py` and `examples/ingest_demo.py`.
- AC5: CI configuration added that runs unit tests fast on PRs and gates integration tests to main/nightly.

---

## Priority

- High: FR1–FR4, FR6, FR7, NFR1–NFR4, AC1–AC3
- Medium: FR5, FR8–FR10, NFR5–NFR7
- Low: NFR8–NFR10, AC4–AC5

---

## Notes and Constraints

- Avoid introducing heavy runtime dependencies into the PR fast path.
- Design provider protocol to allow both sync and future async adapters; initial implementation may be sync-only but should not preclude async extensions.
