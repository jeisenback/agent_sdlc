#!/usr/bin/env python3
"""Run the PRReviewAgent on a pull request and write findings to a markdown file.

This script is designed to be invoked from CI. It uses `DummyLLMProvider` so
no external LLM keys are required. It heuristically generates a JSON response
when the diff contains TODO/FIXME markers; otherwise returns an empty list.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import List

from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.providers import DummyLLMProvider
from agent_sdlc.core.findings import Finding


def generate_findings_from_diff(diff: str) -> List[Finding]:
    findings: List[Finding] = []
    lines = diff.splitlines()
    todos = [l for l in lines if "TODO" in l or "FIXME" in l]
    if todos:
        desc = "\n".join(todos[:10])
        findings.append(
            Finding(
                id="todo-found",
                title="Found TODO / FIXME in diff",
                description=f"Found TODO/FIXME lines:\n{desc}",
                severity="minor",
                tags=["todo", "style"],
            )
        )

    # simple heuristic: if there are deleted lines, warn about potential breaking changes
    deleted = [l for l in lines if l.startswith("-")]
    if deleted:
        findings.append(
            Finding(
                id="deleted-lines",
                title="Deleted lines detected",
                description=(
                    f"The diff contains {len(deleted)} removed lines. Verify this "
                    "does not remove required functionality."
                ),
                severity="medium",
                tags=["delete", "review"],
            )
        )

    return findings


def findings_to_markdown(findings: List[Finding], pr_number: int, pr_title: str) -> str:
    if not findings:
        return f"## PR Review — #{pr_number} {pr_title}\n\nNo findings from automated review."

    parts = [f"## PR Review — #{pr_number} {pr_title}", ""]
    for f in findings:
        parts.append(f"### {f.title} ({f.severity})")
        parts.append(f"- **id**: {f.id}")
        parts.append(f"- **tags**: {', '.join(f.tags or [])}")
        parts.append("")
        parts.append(f"{f.description}")
        parts.append("---")

    return "\n".join(parts)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--title", required=True)
    p.add_argument("--diff-file", required=True)
    p.add_argument("--pr-number", type=int, required=True)
    p.add_argument("--out", default="pr_review_findings.md")
    args = p.parse_args()

    diff = Path(args.diff_file).read_text(encoding="utf8")

    # generate deterministic findings from diff
    findings = generate_findings_from_diff(diff)

    # create a DummyLLMProvider that returns a JSON array of findings so the
    # existing PRReviewAgent can be exercised end-to-end
    findings_json = json.dumps([f.dict() for f in findings])
    provider = DummyLLMProvider(default=findings_json)

    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title=args.title, diff=diff)
    result = agent.run(inp)

    md = findings_to_markdown(result.findings, args.pr_number, args.title)
    out_path = Path(args.out)
    out_path.write_text(md, encoding="utf8")
    print(out_path)


if __name__ == "__main__":
    main()
