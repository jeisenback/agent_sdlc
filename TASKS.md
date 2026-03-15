# Implementation Tasks — agent_sdlc

This file tracks the immediate tasks to bootstrap the package and to make the
repository a reusable project template. Tasks are sequenced so that quality
gates (fast PR CI, linters, pre-commit) are stood up early and heavier
integration work is gated later.

## Phase 0 — Template & bootstrap (goal: fast project creation)
1. Add project generator (`scripts/init_project.py`) that scaffolds a new repo from
   this template (CI, README, package name, optional integration tests).
2. Add `scripts/bootstrap` to create a venv, install dev deps, and run `pytest -q` —
   ensure a developer can get to a green local test quickly.

## Phase 1 — Early quality gates (high priority)
3. Add GitHub Actions CI workflow to run unit tests and lint on PRs (fast gate).
4. Add `pre-commit` hooks and formatting/lint config (`ruff`, `black`, `isort`) so
   code style is enforced pre-commit.
5. Split dependencies into `requirements.txt` (runtime) and `requirements-dev.txt`
   (tests, linters) so CI and bootstrap only install what they need for the fast
   gate.

## Phase 2 — Core primitives & offline tests (must be stable before expanding)
6. Provider abstraction: `ProviderProtocol`, `DummyLLMProvider` (deterministic),
   and `LLMWrapper`.
7. DB adapter interface and `SqliteAdapter` (fast, in-process tests).
8. `with_retry` decorator and retry policy helpers.
9. Unit test coverage for core primitives using dummy provider + sqlite adapter.

## Phase 3 — Agent implementations & examples
10. Implement example agents (`pr_review`, `issue_refinement`) with runner
    scripts (local demo using `DummyLLMProvider`).
11. Add provider adapter stubs (OpenAI / Anthropic placeholders) behind
    `ProviderProtocol` so teams can opt into real providers later.
12. Add `agent_sdlc/examples/` with runnable demos and documentation showing how
    to swap provider implementations.

## Phase 4 — Integration & gated workflows
13. Add `SqlAlchemyAdapter` and integration tests using `testcontainers.postgres`
    (heavy; run on nightly or gated CI only).
14. Add a nightly/integration GitHub Actions job that runs integration tests and
    expensive checks.

## Phase 5 — Developer experience & publishing
15. Add `CONTRIBUTING.md`, `CODEOWNERS`, and detailed developer docs.
16. Add devcontainer/Codespaces config for one-click onboarding (optional).
17. Add CI badges to `README.md`, package metadata, and publishing docs.

## Prioritised next concrete actions (sequenced)
- Implement Phase 1 items immediately (CI, pre-commit, split requirements) so
  quality gates stand up early.
- After CI is in place, complete Phase 2 core primitives and tests to stabilise
  the fast gate.
- Then implement Phase 3 agents and provider stubs; keep heavy integration in
  Phase 4 gated to nightly/main.

If you confirm, I'll implement the CI workflow and `pre-commit` configuration next,
then update `requirements-dev.txt` and the bootstrap script.

## Phase 6 — Enhancement & long-term improvements
18. Template improvements: make `scripts/init_project.py` fully templated (update `pyproject.toml` metadata, license, author fields, and optional extras).
19. Add automated tests for the project generator and CI smoke tests for generated projects.
20. Implement concrete provider adapters for OpenAI and Anthropic with secure env handling and docs.
21. Add a publishing and release workflow (build wheels, tag releases, upload to PyPI or internal artifact store).
22. Add an examples site or docs site (Sphinx or MkDocs) with runnable examples and API reference.
23. Add automated dependency updates (dependabot) and a scheduled security audit job.
24. Add a `devcontainer.json` and Codespaces configuration for one-click cloud dev environments.
25. Add tests that exercise end-to-end flows using the real providers behind feature flags (gated to integration CI).
26. Add a CHANGELOG template, release checklists, and `scripts/release.py` to automate common release tasks.

These enhancement items are lower priority than Phase 1–4 but important for long-term maintainability and adoption.

## Phase 7 — Workflow quality enhancements

### Pre-commit / CI gates
27. Add `mypy --strict` to pre-commit hooks and CI matrix — enforces the type-hints
    requirement from CLAUDE.md. Gate: CI fails on any type error.
28. Add `pytest-cov` coverage gate (≥80%) to CI — a PR that deletes tests should fail.
    Use `--cov=agent_sdlc --cov-fail-under=80` in the test step.
29. Add a commit-message linter pre-commit hook (local hook, no extra package) that
    validates the `<type>(<scope>): <description>` format from CLAUDE.md Git Rules.

### Agents
30. **Architecture review agent** (`agents/arch_review.py`) — triggered by CI on any
    change under `agent_sdlc/`. Checks: no direct SDK import in agents, all public
    functions have type hints, new modules export `__all__`, no cross-agent imports.
    Produces `Finding` list; blockers fail CI.
31. **Assumption checker agent** (`agents/assumption_checker.py`) — runs on PR CI.
    Extracts implicit assumptions from PR title+description+diff and flags unverified
    ones as WARNINGs. Output posted as a separate PR comment section.
32. **Root cause analysis agent** (`agents/rca.py`) — triggered on issues labelled
    `bug`. Structured prompt: symptom → probable cause → fix options → recommendation.
    Runner: `scripts/run_rca.py`. Posts RCA comment to the issue via `gh`.

### Claude skills (slash commands)
33. `/review-pr` skill — runs `PRReviewAgent` against the current branch diff locally,
    prints blocker/warning/suggestion breakdown, exits 1 on blockers. File:
    `.claude/skills/review-pr.md`.
34. `/refine-issue` skill — fetches a GitHub issue via `gh issue view`, runs
    `IssueRefinementAgent`, prints DoR findings. File: `.claude/skills/refine-issue.md`.

### Documentation
35. Add `docs/agents.md` — full agent reference: inputs, outputs, severity meanings,
    how to invoke locally vs CI.
36. Add `AGENTS.md` at repo root — one-pager for contributors: which agents exist,
    what they check, how to run them before opening a PR.