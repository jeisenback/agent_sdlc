"""Runner for the TraceabilityChecker (requirement→issue→PR→test chain).

Local demo (no gh CLI needed when fields are pre-populated):
    python scripts/run_traceability.py --demo

Check a PR:
    python scripts/run_traceability.py --pr 42

Check a PR and post a comment:
    python scripts/run_traceability.py --pr 42 --post-comment

Check an issue:
    python scripts/run_traceability.py --issue 8

Exits 0 if passed (no WARNING or BLOCKER findings); exits 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime

from agent_sdlc.agents.traceability import (
    TraceabilityChecker,
    TraceabilityInput,
    TraceabilityResult,
)
from agent_sdlc.core.findings import FindingSeverity

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


def _check_gh_cli() -> None:
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


def _fetch_pr(pr_number: int) -> TraceabilityInput:
    logger.info("Fetching PR #%d via gh CLI...", pr_number)
    meta_json = _run(
        ["gh", "pr", "view", str(pr_number), "--json", "body,files,number"]
    )
    meta = json.loads(meta_json)
    changed_files = [f["path"] for f in meta.get("files", [])]
    test_files = [f for f in changed_files if f.startswith("tests/")]

    # Also fetch the linked issue body if we can extract an issue number
    issue_body: str | None = None
    issue_number: int | None = None
    pr_body: str = meta.get("body") or ""
    import re

    m = re.search(r"(?:closes|fixes|resolves|refs)\s+#(\d+)", pr_body, re.IGNORECASE)
    if m:
        issue_number = int(m.group(1))
        try:
            issue_json = _run(
                ["gh", "issue", "view", str(issue_number), "--json", "body"],
                check=False,
            )
            issue_body = json.loads(issue_json).get("body") or ""
        except Exception as exc:
            logger.warning("Could not fetch issue #%d: %s", issue_number, exc)

    return TraceabilityInput(
        pr_number=pr_number,
        issue_number=issue_number,
        pr_body=pr_body,
        issue_body=issue_body,
        changed_files=changed_files,
        test_files_changed=test_files,
    )


def _fetch_issue(issue_number: int) -> TraceabilityInput:
    logger.info("Fetching issue #%d via gh CLI...", issue_number)
    meta_json = _run(
        ["gh", "issue", "view", str(issue_number), "--json", "body,number"]
    )
    meta = json.loads(meta_json)
    return TraceabilityInput(
        issue_number=issue_number,
        issue_body=meta.get("body") or "",
    )


def _print_result(result: TraceabilityResult, label: str) -> None:
    print("\n" + "=" * 70)
    print(f"{label} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Status: {'PASSED' if result.passed else 'FAILED'}")
    print(
        f"Findings: {result.warning_count} warning(s), "
        f"{result.suggestion_count} suggestion(s)"
    )
    print("=" * 70)
    for f in result.findings:
        sym = _SEVERITY_SYMBOL[f.severity]
        print(f"[{sym}] {f.rule} @ {f.location}: {f.message}")
        if f.suggestion:
            print(f"     -> {f.suggestion}")
    if not result.findings:
        print("  No findings — traceability chain is intact.")
    print("=" * 70 + "\n")


def _post_comment(pr_number: int, result: TraceabilityResult) -> None:
    status = (
        "**Status: Traceability chain intact**"
        if result.passed
        else "**Status: Traceability gaps found**"
    )
    lines = [f"## Traceability Checker\n\n{status}\n"]
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
    _run(["gh", "pr", "comment", str(pr_number), "--body", body])
    logger.info("Comment posted to PR #%d.", pr_number)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TraceabilityChecker.")
    parser.add_argument("--pr", type=int, metavar="NUMBER")
    parser.add_argument("--issue", type=int, metavar="NUMBER")
    parser.add_argument("--post-comment", action="store_true")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with pre-canned demo data (no gh CLI needed)",
    )
    args = parser.parse_args()

    if args.demo:
        inp = TraceabilityInput(
            pr_number=1,
            pr_body="Closes #42\n\nAdds retry logic.",
            issue_number=42,
            issue_body="See REQUIREMENTS.md for acceptance criteria.",
            changed_files=["agent_sdlc/core/retry.py", "tests/test_retry.py"],
            test_files_changed=["tests/test_retry.py"],
        )
    elif args.pr:
        _check_gh_cli()
        try:
            inp = _fetch_pr(args.pr)
        except Exception as exc:
            logger.error("Failed to fetch PR #%d: %s", args.pr, exc)
            return 1
    elif args.issue:
        _check_gh_cli()
        try:
            inp = _fetch_issue(args.issue)
        except Exception as exc:
            logger.error("Failed to fetch issue #%d: %s", args.issue, exc)
            return 1
    else:
        parser.print_help()
        return 1

    try:
        checker = TraceabilityChecker(inp)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    result = checker.run()
    label = (
        f"PR #{args.pr} Traceability"
        if args.pr
        else f"Issue #{args.issue} Traceability" if args.issue else "Demo Traceability"
    )
    _print_result(result, label)

    if args.pr and args.post_comment:
        try:
            _post_comment(args.pr, result)
        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
