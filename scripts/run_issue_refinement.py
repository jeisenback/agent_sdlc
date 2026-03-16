"""Runner for the Issue Refinement Agent (Definition of Ready check).

Local demo (DummyLLMProvider):
    python scripts/run_issue_refinement.py

CI / production (requires ANTHROPIC_API_KEY and gh CLI):
    python scripts/run_issue_refinement.py --issue 8 --post-comment --update-labels

Exits 0 if DoR passes (ready=True); exits 1 if any BLOCKER findings exist.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime

from agent_sdlc.agents.issue_refinement import IssueInput, IssueRefinementAgent
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider, ProviderProtocol

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

_SEVERITY_SYMBOL = {
    FindingSeverity.BLOCKER: "BLOCKER",
    FindingSeverity.WARNING: "WARNING",
    FindingSeverity.SUGGESTION: "SUGGESTION",
}


def _run(cmd: list[str], check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


_BODY_CHAR_LIMIT = 3000  # keep prompts short enough for reliable JSON responses


def _fetch_issue(issue_number: int) -> IssueInput:
    logger.info("Fetching issue #%d via gh CLI...", issue_number)
    meta_json = _run(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,title,body,labels,milestone,assignees,state",
        ]
    )
    meta = json.loads(meta_json)
    body = meta.get("body") or ""
    if len(body) > _BODY_CHAR_LIMIT:
        body = body[:_BODY_CHAR_LIMIT] + "\n...[truncated for DoR check]"
    return IssueInput(
        title=meta["title"],
        description=body,
    )


def _check_gh_cli() -> None:
    """Exit 1 with a clear message if gh CLI is absent or unauthenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True
        )
        if result.returncode != 0:
            print("gh CLI not available or not authenticated", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("gh CLI not available or not authenticated", file=sys.stderr)
        sys.exit(1)


def _build_provider() -> ProviderProtocol:
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from agent_sdlc.core.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        except Exception as exc:
            logger.warning(
                "Could not load AnthropicProvider (%s) — using DummyLLMProvider.", exc
            )
    print("[INFO] No API key — using DummyLLMProvider", file=sys.stderr)
    return DummyLLMProvider(default="[]")


def _print_result(result, issue_number: int | None = None) -> None:
    label = f"Issue #{issue_number}" if issue_number else "Demo Issue"
    print("\n" + "=" * 70)
    print(f"{label} DoR Check — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Status: {'READY' if result.ready else 'NOT READY'}")
    print(
        f"Findings: {result.blocker_count} blocker(s), {result.warning_count} warning(s), "
        f"{result.suggestion_count} suggestion(s)"
    )
    print("=" * 70)
    for f in result.findings:
        sym = _SEVERITY_SYMBOL[f.severity]
        print(f"[{sym}] DoR:{f.rule} @ {f.location}: {f.message}")
        if f.suggestion:
            print(f"     -> {f.suggestion}")
    if not result.findings:
        print("  No findings — issue is DoR ready.")
    print("=" * 70 + "\n")


def _post_comment(issue_number: int, result) -> None:
    status = (
        "**Status: DoR passed — eligible for sprint planning (human approval required)**"
        if result.ready
        else "**Status: NOT READY — blockers must be resolved before sprint entry**"
    )
    lines = [f"## Issue Refinement Agent (DoR Check)\n\n{status}\n"]
    if result.findings:
        lines.append("| Severity | Location | Rule | Message |")
        lines.append("|----------|----------|------|---------|")
        for f in result.findings:
            msg = f.message.replace("|", "\\|")
            lines.append(
                f"| {f.severity.value} | `{f.location}` | `{f.rule}` | {msg} |"
            )
    else:
        lines.append("_No findings._")
    body = "\n".join(lines)
    _run(["gh", "issue", "comment", str(issue_number), "--body", body])
    logger.info("Comment posted to issue #%d.", issue_number)


def _update_labels(issue_number: int, ready: bool) -> None:
    if ready:
        _run(
            [
                "gh",
                "issue",
                "edit",
                str(issue_number),
                "--remove-label",
                "needs-review",
            ],
            check=False,
        )
    else:
        _run(
            ["gh", "issue", "edit", str(issue_number), "--add-label", "blocked"],
            check=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Issue Refinement Agent (DoR check)."
    )
    parser.add_argument(
        "--issue", type=int, metavar="NUMBER", help="GitHub issue number"
    )
    parser.add_argument("--post-comment", action="store_true")
    parser.add_argument("--update-labels", action="store_true")
    args = parser.parse_args()

    if args.issue:
        _check_gh_cli()
        try:
            inp = _fetch_issue(args.issue)
        except Exception as exc:
            logger.error("Failed to fetch issue #%d: %s", args.issue, exc)
            return 1
    else:
        # Local demo mode
        inp = IssueInput(
            title="Demo: Add retry logic",
            description="Something is broken — needs investigation.",
        )

    provider = _build_provider()
    agent = IssueRefinementAgent(provider)
    result = agent.run(inp)
    _print_result(result, args.issue)

    if args.issue and args.post_comment:
        try:
            _post_comment(args.issue, result)
        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)

    if args.issue and args.update_labels:
        try:
            _update_labels(args.issue, result.ready)
        except Exception as exc:
            logger.error("Failed to update labels: %s", exc)

    return 0 if result.ready else 1


if __name__ == "__main__":
    sys.exit(main())
