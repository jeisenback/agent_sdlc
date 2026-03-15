#!/usr/bin/env python3
"""Run the PRReviewAgent on a pull request and write findings to a markdown file.

Invoked from CI (see .github/workflows/pr_review.yml).  Uses DummyLLMProvider
with structured diff heuristics that produce findings in the canonical Finding
schema (location / severity / rule / message / suggestion).

When ANTHROPIC_API_KEY is set and the real AnthropicProvider is implemented,
swap DummyLLMProvider for it here — no changes required to the agent itself.

Exit codes:
  0 — approved (zero BLOCKER findings)
  1 — one or more BLOCKER findings
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _findings_from_diff(diff: str) -> List[Finding]:
    findings: List[Finding] = []
    lines = diff.splitlines()

    todos = [(i + 1, ln) for i, ln in enumerate(lines) if "TODO" in ln or "FIXME" in ln]
    for lineno, line in todos[:5]:
        findings.append(
            Finding(
                location=f"diff line {lineno}",
                severity=FindingSeverity.WARNING,
                rule="style:todo-fixme",
                message=f"Unresolved marker: {line.strip()}",
                suggestion="Resolve or convert to a tracked issue before merging.",
            )
        )

    deleted = [ln for ln in lines if ln.startswith("-") and not ln.startswith("---")]
    if len(deleted) > 50:
        findings.append(
            Finding(
                location="(diff)",
                severity=FindingSeverity.WARNING,
                rule="review:large-deletion",
                message=(
                    f"{len(deleted)} lines removed — verify no required functionality was dropped."
                ),
                suggestion="Add a PR description note explaining what was removed and why.",
            )
        )

    return findings


def _to_markdown(findings: List[Finding], pr_number: int, pr_title: str) -> str:
    if not findings:
        return (
            f"## PR Review \u2014 #{pr_number} {pr_title}\n\n"
            "No findings from automated review. \u2705"
        )

    _icon = {
        FindingSeverity.BLOCKER: "\U0001f6ab",
        FindingSeverity.WARNING: "\u26a0\ufe0f",
        FindingSeverity.SUGGESTION: "\U0001f4a1",
    }
    parts = [f"## PR Review \u2014 #{pr_number} {pr_title}", ""]
    for f in findings:
        icon = _icon.get(f.severity, "\u2022")
        parts.append(f"### {icon} `{f.rule}` \u2014 **{f.severity.value.upper()}**")
        parts.append(f"**Location:** `{f.location}`")
        parts.append(f"{f.message}")
        if f.suggestion:
            parts.append(f"> **Suggestion:** {f.suggestion}")
        parts.append("")

    blockers = sum(1 for f in findings if f.severity == FindingSeverity.BLOCKER)
    warnings = sum(1 for f in findings if f.severity == FindingSeverity.WARNING)
    suggestions = len(findings) - blockers - warnings
    parts.append(
        f"---\n**Summary:** {blockers} blocker(s) \u00b7 {warnings} warning(s)"
        f" \u00b7 {suggestions} suggestion(s)"
    )
    return "\n".join(parts)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--title", required=True)
    p.add_argument("--diff-file", required=True)
    p.add_argument("--pr-number", type=int, required=True)
    p.add_argument("--out", default="pr_review_findings.md")
    args = p.parse_args()

    diff = Path(args.diff_file).read_text(encoding="utf8")
    heuristic_findings = _findings_from_diff(diff)

    # Serialise heuristic findings as the JSON the DummyLLMProvider will return.
    # PRReviewAgent calls parse_findings_from_json on this payload, so the schema
    # must match Finding exactly (location/severity/rule/message/suggestion).
    findings_json = json.dumps(
        [
            (f.model_dump() if hasattr(f, "model_dump") else f.dict())
            for f in heuristic_findings
        ]
    )

    provider = DummyLLMProvider(default=findings_json)
    agent = PRReviewAgent(provider)
    result = agent.run(PRReviewInput(title=args.title, diff=diff))

    md = _to_markdown(result.findings, args.pr_number, args.title)
    out_path = Path(args.out)
    out_path.write_text(md, encoding="utf8")
    print(md)

    if not result.approved:
        print(
            f"\n\u274c {result.blocker_count} BLOCKER(S) \u2014 failing CI.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
