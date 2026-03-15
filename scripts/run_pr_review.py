"""Runner for the PR Review Agent.

Local demo (DummyLLMProvider):
    python scripts/run_pr_review.py

CI / production (requires ANTHROPIC_API_KEY and gh CLI):
    python scripts/run_pr_review.py --pr 42 --post-comment

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime

from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
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


def _fetch_pr(pr_number: int) -> PRReviewInput:
    logger.info("Fetching PR #%d via gh CLI...", pr_number)
    meta_json = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,body,baseRefName,headRefName,author,files",
        ]
    )
    meta = json.loads(meta_json)
    try:
        diff = _run(["gh", "pr", "diff", str(pr_number)])
    except subprocess.CalledProcessError:
        logger.warning(
            "Could not fetch diff for PR #%d — proceeding without it.", pr_number
        )
        diff = ""
    return PRReviewInput(
        title=meta["title"],
        diff=diff,
        author=meta["author"]["login"],
    )


def _build_provider() -> ProviderProtocol:
    """Return a real provider if credentials are available, else DummyLLMProvider."""
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from agent_sdlc.core.anthropic_provider import AnthropicProvider

            return AnthropicProvider()
        except Exception as exc:
            logger.warning(
                "Could not load AnthropicProvider (%s) — using DummyLLMProvider.", exc
            )
    return DummyLLMProvider(default="[]")


def _print_result(result) -> None:
    print("\n" + "=" * 70)
    print(f"PR Review — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Status: {'APPROVED (no blockers)' if result.approved else 'BLOCKED'}")
    print(
        f"Findings: {result.blocker_count} blocker(s), {result.warning_count} warning(s), "
        f"{result.suggestion_count} suggestion(s)"
    )
    print("=" * 70)
    for f in result.findings:
        sym = _SEVERITY_SYMBOL[f.severity]
        loc = f.location + (f":{f.line_number}" if f.line_number else "")
        print(f"  [{sym}] {f.rule} @ {loc}")
        print(f"     {f.message}")
        if f.suggestion:
            print(f"     → {f.suggestion}")
    if not result.findings:
        print("  No findings.")
    print("=" * 70 + "\n")


def _post_comment(pr_number: int, result) -> None:
    status = (
        "**Status: No blockers — eligible for merge (human approval required)**"
        if result.approved
        else "**Status: BLOCKED — blockers must be resolved before merge**"
    )
    lines = [f"## PR Review Agent\n\n{status}\n"]
    if result.findings:
        lines.append("| Severity | Location | Rule | Message |")
        lines.append("|----------|----------|------|---------|")
        for f in result.findings:
            loc = f.location + (f":{f.line_number}" if f.line_number else "")
            msg = f.message.replace("|", "\\|")
            lines.append(f"| {f.severity.value} | `{loc}` | `{f.rule}` | {msg} |")
    else:
        lines.append("_No findings._")
    body = "\n".join(lines)
    _run(["gh", "pr", "comment", str(pr_number), "--body", body])
    logger.info("Comment posted to PR #%d.", pr_number)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PR Review Agent.")
    parser.add_argument("--pr", type=int, metavar="NUMBER", help="GitHub PR number")
    parser.add_argument("--post-comment", action="store_true")
    args = parser.parse_args()

    if args.pr:
        try:
            inp = _fetch_pr(args.pr)
        except Exception as exc:
            logger.error("Failed to fetch PR #%d: %s", args.pr, exc)
            return 1
    else:
        # Local mode: diff current branch against main
        try:
            diff = _run(["git", "diff", "main...HEAD"])
        except Exception:
            diff = _run(["git", "diff", "HEAD"], check=False)
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], check=False)
        inp = PRReviewInput(title=f"Local review — {branch}", diff=diff)

    provider = _build_provider()
    agent = PRReviewAgent(provider)
    result = agent.run(inp)
    _print_result(result)

    if args.pr and args.post_comment:
        try:
            _post_comment(args.pr, result)
        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
