---
name: refine-issue
description: Run the Issue Refinement Agent (Definition of Ready check) on a GitHub issue or in local demo mode.
usage: /refine-issue [--issue NUMBER] [--post-comment] [--update-labels]
---

Run the Issue Refinement Agent (DoR check) on a GitHub issue and report findings.

## Steps

1. Run the refinement script:
   ```bash
   python scripts/run_issue_refinement.py
   ```

The script will:
- In local demo mode (no `--issue`): run a DoR check on a built-in demo issue using `DummyLLMProvider`
- With `--issue NUMBER`: fetch the issue via `gh` CLI and run a real DoR check (uses `AnthropicProvider` when `ANTHROPIC_API_KEY` is set, otherwise `DummyLLMProvider`)
- Print findings in the format: `[SEVERITY] DoR:<rule-id> @ <location>: <message>`
- Exit 1 if any BLOCKER findings are present; exit 0 if the issue is DoR ready

## Options

To check a specific GitHub issue and post a comment:
```bash
python scripts/run_issue_refinement.py --issue <NUMBER> --post-comment --update-labels
```

| Flag | Effect |
|------|--------|
| `--issue NUMBER` | Fetch and check a real GitHub issue |
| `--post-comment` | Post DoR result as a comment on the issue |
| `--update-labels` | Add `blocked` label if not ready; remove `needs-review` if ready |

## Severity meanings

| Severity | Action required |
|----------|----------------|
| BLOCKER | Must be resolved before sprint entry |
| WARNING | Should be addressed; reviewer judgement required |
| SUGGESTION | Optional improvement |
