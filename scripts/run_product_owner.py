"""Runner for the Product Owner Agent (backlog-grooming strategic review).

Local demo (DummyLLMProvider):
    python scripts/run_product_owner.py

CI / production (requires ANTHROPIC_API_KEY and gh CLI):
    python scripts/run_product_owner.py --issue 8 --post-comment

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime

from agent_sdlc.agents.product_owner import ProductOwnerAgent, ProductOwnerInput
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

_BODY_CHAR_LIMIT = 3000


def _run(cmd: list[str], check: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    return result.stdout.strip()


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


def _fetch_issue(issue_number: int) -> ProductOwnerInput:
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
        body = body[:_BODY_CHAR_LIMIT] + "\n...[truncated for PO review]"
    return ProductOwnerInput(
        title=meta["title"],
        description=body,
    )


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


def _print_result(result: object, issue_number: int | None = None) -> None:
    from agent_sdlc.agents.product_owner import ProductOwnerResult

    assert isinstance(result, ProductOwnerResult)
    label = f"Issue #{issue_number}" if issue_number else "Demo Issue"
    print("\n" + "=" * 70)
    print(f"{label} PO Review — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Status: {'APPROVED' if result.approved else 'NOT APPROVED'}")
    print(
        f"Findings: {result.blocker_count} blocker(s), {result.warning_count} warning(s), "
        f"{result.suggestion_count} suggestion(s)"
    )
    print("=" * 70)
    for f in result.findings:
        sym = _SEVERITY_SYMBOL[f.severity]
        print(f"[{sym}] {f.rule} @ {f.location}: {f.message}")
        if f.suggestion:
            print(f"     -> {f.suggestion}")
    if not result.findings:
        print("  No findings — issue passes PO strategic review.")
    print("=" * 70 + "\n")


def _post_comment(issue_number: int, result: object) -> None:
    from agent_sdlc.agents.product_owner import ProductOwnerResult

    assert isinstance(result, ProductOwnerResult)
    status = (
        "**Status: Strategically approved — eligible for backlog (human PO approval required)**"
        if result.approved
        else "**Status: NOT APPROVED — strategic gaps must be resolved before backlog entry**"
    )
    lines = [f"## Product Owner Agent\n\n{status}\n"]
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Product Owner Agent (strategic backlog-grooming review)."
    )
    parser.add_argument(
        "--issue", type=int, metavar="NUMBER", help="GitHub issue number"
    )
    parser.add_argument("--post-comment", action="store_true")
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
        inp = ProductOwnerInput(
            title="Add retry logic to payment service",
            description="The payment service sometimes fails. We should add retry logic.",
        )

    provider = _build_provider()
    agent = ProductOwnerAgent(provider)
    result = agent.run(inp)
    _print_result(result, args.issue)

    if args.issue and args.post_comment:
        try:
            _post_comment(args.issue, result)
        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
