# CLAUDE.md — agent_sdlc

> **READ `TASKS.md` BEFORE DOING ANYTHING ELSE.**
> It tells you which phase is active, what tasks are in progress, and what to work on next.
> If you skip this step, you will work on the wrong thing.

---

## Project Context

`agent_sdlc` is a Python library of reusable agent-assisted SDLC primitives: LLM provider
abstractions, retry utilities, database adapters, and a growing catalog of review and
governance agents. It is designed so teams can run fast offline unit tests and swap in
production adapters with zero code changes.

**4-component core architecture:**
- `agent_sdlc.core` — retry, logging, types, DB adapter interfaces
- `agent_sdlc.core.llm` — ProviderProtocol + DummyLLMProvider + concrete providers
- `agent_sdlc.agents` — pluggable agents accepting injected provider & adapter
- `agent_sdlc.adapters` — SqliteAdapter, SqlAlchemyAdapter, optional external adapters

**Agent governance layer** (Phase 9+):
- Pipeline Orchestrator — YAML-driven multi-agent coordination (`.agent-pipeline.yml`)
- FindingAggregator — unified output from multiple agents
- AgentReviewAgent — quality gate for new agents before they ship
- ReasoningCheckAgent — verifies BLOCKER findings before they block work
- RoutingOrchestrator — LLM-driven dynamic agent selection (Sprint 3+)

For the full agent catalog and pipeline wiring, see: `docs/agents.md` and `.agent-pipeline.yml`.
For multi-agent context and handoff protocol, see: `pipeline_context.md`.

---

## Session Startup (Do This Every Time — In Order)

```
1. Read TASKS.md              → find active phase, current task, blockers
2. Read DESIGN.md             → confirm module boundaries, public API, CI strategy
3. Read REQUIREMENTS.md       → confirm acceptance criteria for the task you are working
4. Read .agent-pipeline.yml   → understand what is currently wired (if touching agents or CI)
5. git status                 → confirm branch, confirm clean state
6. pytest -q                  → must pass before writing any code
```

If no task is clearly active in `TASKS.md`: do not start work. Ask the human lead what to
work on or which phase to advance to.

---

## Your Role — Moderate Autonomy

You implement within the scope of a clearly defined task. You explain before large changes.
You ask when uncertain about architecture, dependencies, or scope.

**Human lead owns:** architecture decisions, merging PRs, adding dependencies, phase
boundaries, scope changes, any irreversible operation, agent lifecycle approval.

**You own:** implementation within the task, tests for your own code, code quality,
doc updates in scope, commit authorship.

For small, contained changes (docs, config, single-file private fixes with no interface
change), proceed with a concise explanation rather than a full planning step.
When uncertain about scope, ask before writing code.

---

## Decision Authority

| Area | You Decide | Must Ask Human |
|------|-----------|----------------|
| Implementation approach | Algorithm, data structure, function decomposition | Change to a public function signature |
| Testing | Write new tests, fix broken unit tests | Modify a test that exists for a regression/bug fix |
| Code structure | Refactor within a file, rename private functions | Add or remove a module from `agent_sdlc/` |
| Imports | Use packages already in `requirements.txt` | Add any new package (even dev-only) |
| Database | Write parameterized SQL selects and inserts | Change schema, add/modify migrations |
| Documentation | Update in-scope `.md` files and docstrings | Modify DESIGN.md, REQUIREMENTS.md, or this file |
| Commits | Author commit messages in correct format | — |
| Branch work | Work within the current task's branch | Open a branch for a different task |
| Error handling | `try/except` with logging | Swallow exceptions silently |
| **Agent lifecycle** | Run AgentReviewAgent on a new agent | **Ship a new agent without AgentReviewAgent passing** |
| **Pipeline wiring** | Add an agent entry to `.agent-pipeline.yml` | Create a standalone CI trigger outside the pipeline |
| **Rule namespaces** | Use an existing namespace (e.g. `DoR:`, `PO:`) | Introduce a new namespace without checking for collisions |

**When in doubt:** explain what you're about to do and ask. Waiting costs less than rework.

---

## Before-You-Code Checklist

Before writing or editing any source file:

```
[ ] TASKS.md read → active phase confirmed; task confirmed not already claimed
[ ] DESIGN.md read → module boundaries understood for the area you are touching
[ ] REQUIREMENTS.md read → you can list the acceptance criteria from memory
[ ] Test suite passes locally: pytest -q
[ ] Branch name follows convention; branch exists and is clean
[ ] You have READ any file you are about to edit (never modify a file you haven't read)
[ ] If adding a new agent → AgentReviewAgent will be run on it before the PR is opened
[ ] If adding a new CI trigger → it is wired through .agent-pipeline.yml, not standalone
```

---

## Git Rules

**Quick rules:**

| Rule | Value |
|------|-------|
| Branch base | Always from `main` (or `develop` if the repo adopts one) |
| Branch format | `<type>/<phase>-<slug>` (e.g. `feature/p2-provider-protocol`) |
| Commit format | `<type>(<scope>): <description>` |
| Pre-push gate | `pytest -q` must pass; no uncommitted changes |
| Merge | PR only; human reviews and merges |

**Commit types:** `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

---

## Code Standards

```
ALL LLM calls via agent_sdlc.core.providers (ProviderProtocol)  ← never instantiate Anthropic/OpenAI SDK directly in agents
ALL external API calls use with_retry                            ← @with_retry() from agent_sdlc.core.retry
ALL inbound data validated with Pydantic                         ← at every module boundary, before processing
TYPE HINTS on all public functions                               ← params + return type; mypy-compatible
UNIT TESTS run offline                                           ← DummyLLMProvider + SqliteAdapter; no network in pytest -q
POSTGRESQL for production                                        ← DATABASE_URL from env; SQLite = tests only
SECRETS via env vars only                                        ← never store CLAUDE_API_KEY or any key in code or tests
FUNCTIONS < 200 lines                                            ← prefer composition over inheritance
PYTHON 3.10+                                                     ← no language features that break 3.10 compatibility
```

**Agent-specific standards:**
```
ALL new agents export __all__                                    ← [AgentClass, InputModel, ResultModel]
ALL new agents have one unit test per BLOCKER rule               ← DummyLLMProvider, asserts approved=False
ALL new agents wired into .agent-pipeline.yml                    ← no standalone CI triggers
ALL result models gate on BLOCKER findings                       ← approved/ready/passed = no BLOCKERs present
ALL finding rule IDs use the agent's namespace prefix            ← e.g. DoR:, PO:, UX:, AgentReview:
```

---

## Session End Protocol

Do this at the end of **every** session, before closing your terminal:

```
1. Commit all changes to current branch (no uncommitted work left behind)
2. pytest -q → must pass before your final commit
3. Update TASKS.md:
   - Mark completed tasks with ✓ and the date
   - Add a brief note on in-progress state (enough for a different agent to continue)
4. Push branch to remote:
   git push origin <your-branch>
5. If work is complete and all AC met:
   - Run AgentReviewAgent on any new agent files before opening the PR
   - Open PR with a clear description of what was done and which REQUIREMENTS.md items are satisfied
   - Note any follow-on tasks that became visible during the work
```

---

## Hard Stops

> These are absolute. If you reach one of these situations, stop.
> Write what you were about to do, why, and what the alternatives are.
> Do not proceed without explicit human approval.

```
NEVER  add packages to requirements.txt or pyproject.toml
NEVER  merge to main (open the PR; the human merges)
NEVER  close or skip an acceptance criterion without satisfying it
NEVER  instantiate the Anthropic or OpenAI SDK directly inside an agent — use ProviderProtocol
NEVER  git push --force or git push --force-with-lease to main
NEVER  git commit --no-verify
NEVER  change a public function signature outside the explicit scope of the task
NEVER  store secrets, API keys, or tokens in code, tests, or committed config
NEVER  make network calls in unit tests (use DummyLLMProvider + SqliteAdapter)
NEVER  silently swallow exceptions — log and surface them
NEVER  ship a new agent without AgentReviewAgent (individual) passing zero BLOCKERs
NEVER  create a standalone CI trigger for a new agent — wire it into .agent-pipeline.yml
NEVER  introduce a new rule namespace without first checking for collisions via AgentReview:sys:namespace-collision
NEVER  hardcode a BLOCKER severity in a new agent without a corresponding unit test asserting approved=False
```

---

## Reference Map

| What You Need | Where to Find It |
|---------------|-----------------|
| Active phase, current task, blockers | `TASKS.md` ← **read first** |
| Module boundaries, public API, CI strategy | `DESIGN.md` |
| Functional + non-functional requirements, AC | `REQUIREMENTS.md` |
| Agent catalog — all agents, inputs, outputs, rules | `docs/agents.md` (Sprint 5) / GitHub issues until then |
| Pipeline wiring — what triggers what | `.agent-pipeline.yml` |
| Multi-agent context and handoff protocol | `pipeline_context.md` |
| Liveness/health probe design (provider + DB) | `heartbeat.md` |
| Agent output quality metrics and health | `docs/agent_health.md` (Sprint 4) |
| Single-agent session lifecycle | `session.md` |
| LLM provider abstraction and retry usage | `agent_sdlc/core/providers.py`, `agent_sdlc/core/retry.py` |
| DB adapter interface and implementations | `agent_sdlc/core/db.py` |
| Finding schema shared by all agents | `agent_sdlc/core/findings.py` |
| Unit tests | `tests/` |
| Copilot usage and coding style | `copilot_instructions.md` |
| Run unit tests | `pytest -q` |
