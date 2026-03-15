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

## Phase 8 — Expanded agent suite

### Sprint 2 agents (offline-capable with DummyLLMProvider)
37. **ProcessGapAgent — issue-level** (`agents/process_gap.py`, mode=issue) — runs
    alongside IssueRefinementAgent. Checks business-side gaps: no stated "why",
    no success metric, no target user, scope creep risk, no rollback plan.
    Rules namespace: `biz:`. Runner: `scripts/run_process_gap.py`.
38. **PromptReviewAgent** (`agents/prompt_review.py`) — reviews LLM prompt strings
    in `agent_sdlc/agents/**` for quality: format specified, no injection vector,
    fallback defined, role framing present. Rules namespace: `Prompt:`.
    CI trigger: PR paths `agent_sdlc/agents/**`. Runner: `scripts/run_prompt_review.py`.
39. **ProductOwnerAgent** (`agents/product_owner.py`) — backlog-grooming gate (runs
    before DoR). Checks strategic alignment: value unclear, no target user, unmeasurable
    success, scope creep, feature overlap. Rules namespace: `PO:`.
    Runner: `scripts/run_product_owner.py`.
40. **DiagramAgent** (`agents/diagram.py`) — generates Mermaid diagrams from structured
    input (agent flow, module deps, sequence, ER). Output embeds directly in GitHub
    PR/issue comments as ```mermaid blocks. Runner: `scripts/run_diagram.py`.

### Sprint 3 agents (benefits from real LLM)
41. **ProcessGapAgent — workflow-level** (extend task 37, mode=workflow) — analyses
    repo-wide process artifacts (CLAUDE.md, CI workflows, CODEOWNERS, issue patterns)
    for dev workflow gaps: no DoD, no deploy smoke, no incident runbook, no feature
    flags strategy. Runs weekly via scheduled CI; posts gap report to pinned issue.
42. **TraceabilityChecker** (`agents/traceability.py`) — supporting agent. Checks the
    chain: Requirement → Issue → PR → Test → Deploy tag. Flags broken links.
    Feeds into the workflow-level ProcessGapAgent report.
43. **UXAgent** (`agents/ux.py`) — reviews user flow descriptions for friction: no
    error state, no success feedback, dead ends, ambiguous CTAs, missing undo on
    destructive actions. Input: prose flow + user goal. Rules namespace: `UX:`.
    Runner: `scripts/run_ux.py`.

### Sprint 5 agents (specialized / polish)
44. **UIDesignAgent** (`agents/ui_design.py`) — reviews UI source (HTML/JSX/CSS) or
    design specs for visual consistency and accessibility: color contrast (WCAG AA),
    hardcoded colors/spacing outside design tokens, missing alt text, responsive gaps.
    Rules namespace: `UI:`. Runner: `scripts/run_ui_design.py`.

### Supporting infrastructure (Sprint 3)
45. **FindingAggregator** (`agents/finding_aggregator.py`) — merges Finding lists from
    multiple agents, deduplicates, resolves severity conflicts, produces one unified
    comment. Required once 3+ review agents post to the same PR.
46. **IssueLinker** supporting agent — given a set of findings, searches open GitHub
    issues for related ones and appends links. Prevents duplicate work.
47. `/process-gaps` Claude skill — runs ProcessGapAgent (workflow-level) locally
    against the current repo. File: `.claude/skills/process-gaps.md`.

### Sprint 4 supporting (ops)
48. **SprintHealthReporter** — weekly scheduled job: counts open blockers across
    milestone issues, flags stale issues (no activity > 7 days), posts summary to
    a pinned GitHub issue. Uses `gh` CLI; no LLM required.

## Phase 9 — Agent Governance Layer

This phase introduces meta-agents that manage, coordinate, and quality-gate the
agent system itself. Build order within Sprint 2 matters: infrastructure first,
then the review agent (used to validate everything built after it), then core agents.

### Sprint 2 — governance infrastructure (build in this order)
49. **FindingAggregator** (move from Phase 8 / Sprint 6) — required by the pipeline
    orchestrator on day one. Merges Finding lists from multiple agents, deduplicates,
    resolves severity conflicts, produces one unified PR/issue comment.
    No LLM required — deterministic. `agents/finding_aggregator.py`.
50. **Pipeline Orchestrator** — YAML config (`.agent-pipeline.yml`) that maps triggers
    to agent sequences (parallel or sequential). Runner `scripts/run_pipeline.py`
    reads the config and executes agents, routing all output through FindingAggregator
    into a single comment. No LLM required. Handles agent failures per config
    (`on_failure: continue|abort`).
51. **Agent Review Agent — individual mode** (`agents/agent_review.py`, mode=individual)
    — reviews a single agent's source code, prompt string, test file, and CI trigger
    for: prompt quality, pattern compliance (ProviderProtocol, Finding schema, retry),
    test coverage of each BLOCKER rule, `__all__` export. BLOCKER findings block the
    PR that introduces the agent. Applied to every Sprint 2+ agent before it ships.
    Rules namespace: `AgentReview:`.
52. **Reasoning Check Agent** (`agents/reasoning_check.py`) — scaffold Sprint 2,
    activate Sprint 3 (requires real LLM). Triggers when: upstream agent produces ≥1
    BLOCKER finding, issue labelled `planning`, or detected agent error/miscommunication.
    Takes original artifact + upstream findings; verifies each finding's logic is sound,
    severity is justified, and no obvious findings are missing. May downgrade or remove
    hallucinated BLOCKERs. BLOCKER from ReasoningCheck blocks merge.
    Rules namespace: `Reason:`.

### Sprint 3 — governance with real LLM
53. **Routing Orchestrator** — LLM-driven extension of the Pipeline Orchestrator.
    Given event context (what changed, what label, what triggered), decides dynamically
    which agents to invoke and in what order. Falls back to YAML pipeline config when
    LLM unavailable. `agents/routing_orchestrator.py`.
54. **Agent Review Agent — system-level mode** (extend task 51, mode=system) — given
    the full agent catalog (all agent source + prompts), checks for: overlapping rules
    at conflicting severities, gaps in coverage, missing integration points, inconsistent
    naming across namespaces, agents with no CI trigger. Posts a system health report
    to the Sprint Health Dashboard issue. Runs weekly.

### Sprint 4 — meta-agents (patterns stable)
55. **New Agent Agent** (`agents/new_agent.py`) — given a description of desired agent
    behaviour, generates scaffolded files: agent.py, runner script, unit tests, CI
    trigger snippet, pipeline YAML entry. Validates output against AgentReviewAgent
    (individual) rules before returning. Patterns must be stable from Sprint 2+3 first.
56. **Agent Conflict Resolver** (`agents/conflict_resolver.py`) — given findings from
    multiple agents on the same artifact, detects contradictions (same rule, different
    severity) and duplicates (same meaning, different rule ID). Produces adjudicated
    finding set. Feeds into FindingAggregator as a pre-processing step.
57. **Agent Health Monitor** — tracks agent output quality over time: how often BLOCKER
    findings are acted on vs dismissed, which rules are chronic false positives, which
    agents have the highest dismiss rate. Analyses GitHub issue/PR history via `gh`.
    No LLM required. Weekly report to Sprint Health Dashboard.