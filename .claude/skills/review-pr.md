Run the PR Review Agent on the current branch diff and report findings.

## Steps

1. Run the review script:
   ```bash
   python scripts/run_pr_review.py
   ```

The script will:
- Diff the current branch against `main` (`git diff main...HEAD`)
- Run `PRReviewAgent` on the diff (uses `AnthropicProvider` when `ANTHROPIC_API_KEY` is set, otherwise `DummyLLMProvider`)
- Print findings grouped by severity — **BLOCKER** first, then WARNING, then SUGGESTION
- Exit 1 if any BLOCKER findings are present; exit 0 if none

## Options

To review a specific GitHub PR and post a comment:
```bash
python scripts/run_pr_review.py --pr <NUMBER> --post-comment
```

## Severity meanings

| Severity | Action required |
|----------|----------------|
| BLOCKER | Must be resolved before merge |
| WARNING | Should be addressed; reviewer judgement required |
| SUGGESTION | Optional improvement |
