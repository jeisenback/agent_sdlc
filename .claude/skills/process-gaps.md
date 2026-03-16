---
name: process-gaps
description: Run workflow-level process gap analysis on the current repo
usage: /process-gaps
---

Run the ProcessGapAgent in workflow mode against the current repo and print a structured gap report.

## Steps

1. Run the workflow gap analysis:
   ```bash
   PYTHONPATH=. python scripts/run_process_gap.py --mode workflow
   ```

The script will:
- Collect repo artifacts: `CLAUDE.md`, all `.github/workflows/*.yml` files, `CODEOWNERS` (if present), `TASKS.md`
- Pass artifacts to `ProcessGapAgent` in workflow mode
- Print findings grouped: BLOCKERs first, then WARNINGs, then SUGGESTIONs
- Use `DummyLLMProvider` when `ANTHROPIC_API_KEY` is not set (prints `[INFO] No API key — using DummyLLMProvider` to stderr)
- Exit 1 if any BLOCKER process gaps are found; exit 0 otherwise

## Output format

```
[SEVERITY] dev|biz:<rule-id> @ <location>: <message>
```

Example:
```
[BLOCKER] dev:no-ci-on-pr @ .github/workflows/ — No PR-triggered CI workflow found
[WARNING] biz:no-definition-of-done @ CLAUDE.md — No explicit DoD section detected
[SUGGESTION] dev:missing-codeowners @ CODEOWNERS — No CODEOWNERS file found
```

## Options

| Flag | Effect |
|------|--------|
| `--mode workflow` | Analyse repo-level CI/process gaps (default) |
| `--mode issue` | Analyse a single issue for business gap (requires `--title` and `--description`) |
| `--title TEXT` | Issue title (required for `--mode issue`) |
| `--description TEXT` | Issue description (required for `--mode issue`) |

## Severity meanings

| Severity | Action required |
|----------|----------------|
| BLOCKER | Critical process gap; must be resolved before next sprint |
| WARNING | Should be addressed; team lead judgement required |
| SUGGESTION | Optional improvement |
