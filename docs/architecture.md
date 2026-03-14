# Architecture & Design

This repository provides small, composable building blocks for AI-assisted SDLC:

- `agent_sdlc.core.providers` — `ProviderProtocol`, `ProviderResponse`, and `DummyLLMProvider`.
- `agent_sdlc.core.db` — `DBAdapter` protocol and `SqliteAdapter` implementation for fast tests.
- `agent_sdlc.core.retry` — retry helpers used by network adapters.
- `agent_sdlc.agents` — example agents (PR review, issue refinement) that accept a `ProviderProtocol` and `DBAdapter` implementations as dependencies.

Design goals: testability (no network by default), small surface area, and clear extension points for production provider adapters.
