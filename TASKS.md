# Implementation Tasks — agent_sdlc

This file tracks the immediate tasks to bootstrap the package. Tasks are ordered and scoped for short iterations.

## Phase 1 — Bootstrap (this PR)
1. Create package skeleton and metadata (`pyproject.toml`, `requirements.txt`, `README.md`) — estimate: 0.5h
2. Add `DESIGN.md` and `TASKS.md` (this file) — estimate: 0.25h

## Phase 2 — Core extraction
3. Extract `with_retry` and logging helpers to `agent_sdlc.core` — 1–2h
4. Add `ProviderProtocol` and `DummyLLMProvider` — 1h
5. Add DB adapter interfaces and `SqliteAdapter` — 2h

## Phase 3 — Agent refactor & tests
6. Refactor `feature_generation` agent to accept injected adapters — 2–4h
7. Write unit tests using dummy provider + sqlite adapter — 2h
8. Update CI to run unit tests on PRs; add gated integration workflow — 1–2h

## Phase 4 — Integration & polishing
9. Add `SqlAlchemyAdapter` and optional integration tests using `testcontainers.postgres` — 4–8h
10. Migration sweep across repos and compatibility shims — 4–8h
11. Docs, examples, and publishable packaging (optional) — 2–4h

## Next concrete actions (what I'll do now)
- Create `agent_sdlc` package directory and a minimal `__init__.py`.
- Add a `tests/` dir placeholder and a `README.md` with quick start.
 - Add shared `Finding` types under `agent_sdlc/core/findings.py`.
 - Add `LLMWrapper` using `ProviderProtocol` under `agent_sdlc/core/llm_wrapper.py`.
 - Implement `pr_review` and `issue_refinement` agents under `agent_sdlc/agents/`.
 - Add simple runner scripts in `scripts/` for local demos.
 - Add unit tests for both agents using `DummyLLMProvider`.
 - Update this TODO list to reflect the added agents and tests.
