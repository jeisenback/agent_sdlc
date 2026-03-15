# Pipeline Context — Multi-Agent Handoff Protocol

This document defines how context and findings flow between agents in a pipeline
execution. It is the contract that Pipeline Orchestrator, FindingAggregator,
ReasoningCheckAgent, and all review agents implement against.

For single-agent session lifecycle (session_id, context window, DB persistence),
see `session.md`. For liveness probes, see `heartbeat.md`.

---

## Concepts

### Pipeline run
A single execution of `.agent-pipeline.yml` triggered by a GitHub event. Each run
has a `pipeline_run_id` (UUID) and produces a `PipelineContext` that accumulates
findings as agents complete.

### Agent step
One agent invocation within a pipeline run. An agent step:
- Receives: the original artifact (diff, issue body, source file) + any upstream findings
- Produces: a `List[Finding]` written to a named output file
- Declares: success (exit 0) or failure (exit 1) — distinct from finding severity

### Handoff
The structured transfer of a step's findings to the next step or to
`FindingAggregator`. Defined by the wire format below.

---

## Wire Format

Each agent step writes its findings to `--out <step_name>.findings.json`:

```json
{
  "pipeline_run_id": "uuid",
  "agent": "pr_review",
  "step": "sequential-0",
  "artifact_type": "diff",
  "findings": [
    {
      "location": "agent_sdlc/agents/pr_review.py:52",
      "severity": "blocker",
      "rule": "code:no-type-hints",
      "message": "Public function run() missing return type annotation.",
      "suggestion": "Add -> PRReviewResult return type."
    }
  ],
  "approved": false,
  "blocker_count": 1,
  "warning_count": 0,
  "suggestion_count": 0,
  "exit_code": 1,
  "duration_ms": 4200
}
```

`FindingAggregator` collects all `*.findings.json` files from a run and merges them.
`ReasoningCheckAgent` reads upstream `*.findings.json` when `blocker_count > 0`.

---

## Context Accumulation

Agents in a `sequential` step can read upstream findings by receiving
`--upstream <step_name>.findings.json`. The Pipeline Orchestrator passes this
automatically when `consumes_upstream: true` is set in `.agent-pipeline.yml`.

```yaml
pipelines:
  pull_request:
    steps:
      - parallel:
          - agent: arch_review
          - agent: prompt_review
      - sequential:
          - agent: reasoning_check
            consumes_upstream: true   # receives arch_review + prompt_review findings
            trigger_on: blocker_present
      - always:
          - agent: finding_aggregator
```

---

## Context Boundaries

| What passes between agents | What does NOT pass |
|---|---|
| `List[Finding]` in wire format | Raw LLM prompt/response text |
| Artifact path (file or URL) | Internal agent state |
| `pipeline_run_id` | Session context from `session.md` |
| `trigger_reason` (for ReasoningCheck) | Provider credentials |

Agents must never read each other's source or internal state directly — only the
declared wire format output.

---

## Failure Modes

| Scenario | Behaviour |
|---|---|
| Agent exits 1, `on_failure: continue` | Step skipped; empty findings for that agent; pipeline continues |
| Agent exits 1, `on_failure: abort` | Pipeline stops; partial findings posted; comment marked `[PARTIAL]` |
| Agent produces invalid JSON | Findings treated as empty; warning logged in pipeline run summary |
| ReasoningCheck downgrades all BLOCKERs | Downstream sees zero BLOCKERs; pipeline may proceed |
| Two agents contradict (future: ConflictResolver) | Both finding sets passed to ConflictResolver before FindingAggregator |

---

## Pipeline Run Lifecycle

```
GitHub event
    │
    ▼
run_pipeline.py reads .agent-pipeline.yml
    │
    ▼
pipeline_run_id generated; run/ directory created
    │
    ├── parallel steps → agent A.findings.json, agent B.findings.json
    │
    ├── sequential steps (with upstream) → reasoning_check.findings.json
    │
    └── always steps → finding_aggregator produces unified_comment.md
                        diagram produces diagram.md (if configured)
                        unified_comment.md posted to PR/issue via gh
```

---

## Implementation Status

> **STUB** — This document defines the target design.
> Implementation begins with Pipeline Orchestrator (task 50 / issue #52, Sprint 2).

| Component | Status | Issue |
|---|---|---|
| Wire format schema | Designed (this doc) | — |
| Pipeline Orchestrator | Planned | #52 |
| FindingAggregator | Planned | #47 |
| ReasoningCheckAgent | Planned | #54 |
| `consumes_upstream` flag | Planned | #52 |
| ConflictResolver pre-processing | Planned | #58 |

---

## Open Questions (resolve before Pipeline Orchestrator implementation)

1. **Artifact passing** — should agents receive the artifact as a file path or inline
   content? File path is cleaner for large diffs; inline is simpler for issues.
   *Current assumption: file path via `--artifact-file <path>`.*

2. **Parallel output collection** — when parallel steps run as subprocesses, the
   orchestrator polls for `*.findings.json` files. Should it use a shared temp
   directory per `pipeline_run_id` or named pipes?
   *Current assumption: shared temp directory `runs/<pipeline_run_id>/`.*

3. **ReasoningCheck trigger threshold** — currently "any BLOCKER". Should the threshold
   be configurable per pipeline (e.g. only trigger if blocker_count >= 2)?
   *Decision: configurable in `.agent-pipeline.yml` as `trigger_on: blocker_count >= 1`.*

4. **Comment format when partial** — if a step aborts, FindingAggregator receives
   incomplete findings. Should the comment clearly mark which agents did not run?
   *Current assumption: yes — include a "Did not run" section with agent name and reason.*
