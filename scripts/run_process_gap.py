"""Runner for the Process Gap Agent (business context and workflow gap checks).

Local demo — issue mode (DummyLLMProvider):
    python scripts/run_process_gap.py

Check a GitHub issue:
    python scripts/run_process_gap.py --issue 8 --post-comment

Workflow gap analysis (requires ANTHROPIC_API_KEY and gh CLI):
    python scripts/run_process_gap.py --mode workflow --post-report

Exits 0 if no BLOCKER findings; exits 1 if any BLOCKERs exist.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from agent_sdlc.agents.process_gap import (
    ProcessGapAgent,
    ProcessGapInput,
    WorkflowGapInput,
)
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
_WORKFLOW_CHAR_LIMIT = 6000


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


def _fetch_issue(issue_number: int) -> ProcessGapInput:
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
        body = body[:_BODY_CHAR_LIMIT] + "\n...[truncated for process gap check]"
    return ProcessGapInput(
        title=meta["title"],
        description=body,
    )


def _collect_workflow_input() -> WorkflowGapInput:
    """Collect repo-wide artifacts for workflow-level analysis."""
    logger.info("Collecting repository process artifacts...")

    # CLAUDE.md
    claude_md = ""
    claude_path = Path("CLAUDE.md")
    if claude_path.exists():
        text = claude_path.read_text(encoding="utf-8")
        claude_md = text[:_WORKFLOW_CHAR_LIMIT]
    else:
        claude_md = "(CLAUDE.md not found)"

    # CI workflows
    ci_workflows: list[str] = []
    for wf_path in sorted(Path(".github/workflows").glob("*.yml")):
        content = wf_path.read_text(encoding="utf-8")
        ci_workflows.append(f"# {wf_path.name}\n{content[:2000]}")

    # CODEOWNERS
    codeowners: str | None = None
    for co_path in [Path("CODEOWNERS"), Path(".github/CODEOWNERS")]:
        if co_path.exists():
            codeowners = co_path.read_text(encoding="utf-8")[:1000]
            break

    # TASKS.md
    tasks_md: str | None = None
    tasks_path = Path("TASKS.md")
    if tasks_path.exists():
        tasks_md = tasks_path.read_text(encoding="utf-8")[:3000]

    # Recent PR stats via gh CLI
    recent_pr_stats: str | None = None
    try:
        recent_pr_stats = _run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--limit",
                "20",
                "--json",
                "number,title,state,mergedAt,labels,reviewDecision",
            ],
            check=False,
        )
    except Exception as exc:
        logger.warning("Could not fetch PR stats: %s", exc)

    # Recent issue stats via gh CLI
    issue_stats: str | None = None
    try:
        issue_stats = _run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "all",
                "--limit",
                "20",
                "--json",
                "number,title,state,labels,milestone",
            ],
            check=False,
        )
    except Exception as exc:
        logger.warning("Could not fetch issue stats: %s", exc)

    return WorkflowGapInput(
        claude_md=claude_md,
        ci_workflows=ci_workflows,
        codeowners=codeowners,
        tasks_md=tasks_md,
        recent_pr_stats=recent_pr_stats,
        issue_stats=issue_stats,
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


def _print_result(result: object, label: str) -> None:
    from agent_sdlc.agents.process_gap import ProcessGapResult

    assert isinstance(result, ProcessGapResult)
    print("\n" + "=" * 70)
    print(f"{label} — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
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
        print("  No findings.")
    print("=" * 70 + "\n")


def _build_workflow_report(result: object, timestamp: str) -> str:
    """Build a markdown report for posting to the Process Health Dashboard issue."""
    from agent_sdlc.agents.process_gap import ProcessGapResult

    assert isinstance(result, ProcessGapResult)
    status = "✅ No blockers" if result.approved else "🚨 Blockers present"
    lines = [
        f"## Process Health Dashboard — {timestamp}\n",
        f"**{status}** — "
        f"{result.blocker_count} blocker(s) / {result.warning_count} warning(s) / "
        f"{result.suggestion_count} suggestion(s)\n",
    ]
    if result.findings:
        lines.append("| Severity | Rule | Location | Message |")
        lines.append("|----------|------|----------|---------|")
        for f in result.findings:
            msg = f.message.replace("|", "\\|")
            lines.append(
                f"| {f.severity.value} | `{f.rule}` | `{f.location}` | {msg} |"
            )
    else:
        lines.append("_No gaps found this week._")
    return "\n".join(lines)


def _post_issue_comment(issue_number: int, body: str) -> None:
    _run(["gh", "issue", "comment", str(issue_number), "--body", body])
    logger.info("Report posted to issue #%d.", issue_number)


def _post_comment(issue_number: int, result: object) -> None:
    from agent_sdlc.agents.process_gap import ProcessGapResult

    assert isinstance(result, ProcessGapResult)
    status = (
        "**Status: Business context complete — eligible for sprint planning (human approval required)**"
        if result.approved
        else "**Status: NOT APPROVED — business context gaps must be resolved before sprint entry**"
    )
    lines = [f"## Process Gap Agent\n\n{status}\n"]
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
        description="Run the Process Gap Agent (issue or workflow mode)."
    )
    parser.add_argument(
        "--mode",
        choices=["issue", "workflow"],
        default="issue",
        help="Analysis mode (default: issue)",
    )
    parser.add_argument(
        "--issue", type=int, metavar="NUMBER", help="GitHub issue number (issue mode)"
    )
    parser.add_argument(
        "--post-comment",
        action="store_true",
        help="Post findings as issue comment (issue mode)",
    )
    parser.add_argument(
        "--post-report",
        type=int,
        metavar="NUMBER",
        help="Post workflow gap report as comment on this issue number",
    )
    args = parser.parse_args()

    provider = _build_provider()
    agent = ProcessGapAgent(provider)

    if args.mode == "workflow":
        _check_gh_cli()
        inp = _collect_workflow_input()
        result = agent.run(inp)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        _print_result(result, f"Workflow Gap Report — {timestamp}")
        if args.post_report:
            try:
                report = _build_workflow_report(result, timestamp)
                _post_issue_comment(args.post_report, report)
            except Exception as exc:
                logger.error("Failed to post report: %s", exc)
        return 0 if result.approved else 1

    # issue mode
    if args.issue:
        _check_gh_cli()
        try:
            inp_issue = _fetch_issue(args.issue)
        except Exception as exc:
            logger.error("Failed to fetch issue #%d: %s", args.issue, exc)
            return 1
    else:
        inp_issue = ProcessGapInput(
            title="Demo: Add retry logic to payment service",
            description="The payment service sometimes fails. We should add retry logic.",
        )

    result = agent.run(inp_issue)
    label = (
        f"Issue #{args.issue} Process Gap Check"
        if args.issue
        else "Demo Issue Process Gap Check"
    )
    _print_result(result, label)

    if args.issue and args.post_comment:
        try:
            _post_comment(args.issue, result)
        except Exception as exc:
            logger.error("Failed to post comment: %s", exc)

    return 0 if result.approved else 1


if __name__ == "__main__":
    sys.exit(main())
