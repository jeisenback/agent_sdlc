"""Runner for the Diagram Agent (Mermaid diagram generation).

Local demo (DummyLLMProvider):
    python scripts/run_diagram.py

Generate and write to file:
    python scripts/run_diagram.py --type sequence \\
        --description "User logs in, auth service validates token, returns session" \\
        --out diagram.md

Post to a PR comment:
    python scripts/run_diagram.py --type flowchart \\
        --description "Agent pipeline: PO review -> process gap -> DoR check" \\
        --post-pr-comment 42

Post to an issue comment:
    python scripts/run_diagram.py --type erDiagram \\
        --description "User has many Orders; Order has many LineItems" \\
        --post-issue-comment 8
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from agent_sdlc.agents.diagram import DiagramAgent, DiagramInput
from agent_sdlc.core.providers import DummyLLMProvider, ProviderProtocol

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s"
)
logger = logging.getLogger(__name__)

_VALID_TYPES: list[str] = [
    "sequence",
    "flowchart",
    "classDiagram",
    "erDiagram",
    "agentFlow",
]

_DEMO_DESCRIPTION = (
    "Show the agent pipeline: ProductOwnerAgent reviews the issue first, "
    "then ProcessGapAgent checks business context, "
    "then IssueRefinementAgent performs the DoR check. "
    "Each agent produces findings; blockers stop the pipeline."
)


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
    return DummyLLMProvider(default="flowchart TD\n    A[Start] --> B[End]")


def _wrap_in_fences(mermaid_syntax: str, title: str) -> str:
    return f"**{title}**\n\n```mermaid\n{mermaid_syntax}\n```\n"


def _post_comment(number: int, body: str, target: str) -> None:
    """Post body as a comment to a PR or issue."""
    cmd = ["gh", target, "comment", str(number), "--body", body]
    _run(cmd)
    logger.info("Comment posted to %s #%d.", target, number)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Diagram Agent.")
    parser.add_argument(
        "--type",
        dest="diagram_type",
        choices=_VALID_TYPES,
        default="flowchart",
        help="Diagram type (default: flowchart)",
    )
    parser.add_argument(
        "--description", default=_DEMO_DESCRIPTION, help="Prose description to diagram"
    )
    parser.add_argument(
        "--context", default=None, help="Optional context (names, etc.)"
    )
    parser.add_argument("--title", default=None, help="Optional diagram title")
    parser.add_argument(
        "--out", metavar="FILE", default=None, help="Write output to this file"
    )
    parser.add_argument("--post-pr-comment", type=int, metavar="NUMBER", default=None)
    parser.add_argument(
        "--post-issue-comment", type=int, metavar="NUMBER", default=None
    )
    args = parser.parse_args()

    if args.post_pr_comment or args.post_issue_comment:
        _check_gh_cli()

    provider = _build_provider()
    agent = DiagramAgent(provider)

    inp = DiagramInput(
        diagram_type=args.diagram_type,  # type: ignore[arg-type]
        description=args.description,
        context=args.context,
        title=args.title,
    )
    result = agent.run(inp)

    fenced = _wrap_in_fences(result.mermaid_syntax, result.title)
    print(fenced)

    if args.out:
        Path(args.out).write_text(fenced, encoding="utf-8")
        logger.info("Diagram written to %s.", args.out)

    if args.post_pr_comment:
        try:
            _post_comment(args.post_pr_comment, fenced, "pr")
        except Exception as exc:
            logger.error("Failed to post PR comment: %s", exc)
            return 1

    if args.post_issue_comment:
        try:
            _post_comment(args.post_issue_comment, fenced, "issue")
        except Exception as exc:
            logger.error("Failed to post issue comment: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
