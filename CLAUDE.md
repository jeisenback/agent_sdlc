# CLAUDE.md — agent_sdlc

> **READ `TASKS.md` BEFORE DOING ANYTHING ELSE.**
> It tells you which phase is active, what tasks are in progress, and what to work on next.
> If you skip this step, you will work on the wrong thing.

---

## Project Context

`agent_sdlc` is a lightweight Python library that extracts reusable agent-assisted SDLC
primitives: LLM provider abstractions, retry utilities, and database adapters. It is
designed so teams can run fast offline unit tests and swap in production adapters with
zero code changes.

The package is a 4-component architecture:
- `agent_sdlc.core` — retry, logging, types, DB adapter interfaces
- `agent_sdlc.core.llm` — ProviderProtocol + DummyLLMProvider + concrete providers
- `agent_sdlc.agents` — pluggable agents accepting injected provider & adapter
- `agent_sdlc.adapters` — SqliteAdapter, SqlAlchemyAdapter, optional external adapters

Phases: Phase 1 (bootstrap) → Phase 2 (core extraction) → Phase 3 (agent refactor & tests) → Phase 4 (integration & polishing).

---

## Session Startup (Do This Every Time — In Order)

```
1. Read TASKS.md        → find active phase, current task, blockers
2. Read DESIGN.md       → confirm module boundaries, public API, CI strategy
3. Read REQUIREMENTS.md → confirm acceptance criteria for the task you are working
4. git status           → confirm branch, confirm clean state
5. pytest -q            → must pass before writing any code
```

If no task is clearly active in `TASKS.md`: do not start work. Ask the human lead what to
work on or which phase to advance to.

---

## Your Role — Moderate Autonomy

You implement within the scope of a clearly defined task. You explain before large changes.
You ask when uncertain about architecture, dependencies, or scope.

**Human lead owns:** architecture decisions, merging PRs, adding dependencies, phase
boundaries, scope changes, any irreversible operation.

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
```

---

## Reference Map

| What You Need | Where to Find It |
|---------------|-----------------|
| Active phase, current task, blockers | `TASKS.md` ← **read first** |
| Module boundaries, public API, CI strategy | `DESIGN.md` |
| Functional + non-functional requirements, AC | `REQUIREMENTS.md` |
| Liveness/health probe design | `heartbeat.md` |
| Session lifecycle and context management | `session.md` |
| LLM provider abstraction and retry usage | `agent_sdlc/core/providers.py`, `agent_sdlc/core/retry.py` |
| DB adapter interface and implementations | `agent_sdlc/core/db.py` |
| Unit tests | `tests/` |
| Claude provider integration guidance | `CLAUDE.md` (this file) |
| Copilot usage and coding style | `copilot_instructions.md` |
| Run unit tests | `pytest -q` |
