"""agent_sdlc/agents/issue_linker.py

IssueLinker — deterministic agent that enriches BLOCKER/WARNING findings
with links to semantically related open GitHub issues.

No LLM required — uses gh CLI search only.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any, Dict, List

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LinkerInput(BaseModel):
    findings: List[Finding]
    repo: str  # "owner/repo"


class LinkedResult(BaseModel):
    findings: List[Finding]
    related_issues: Dict[str, List[Dict[str, Any]]]  # rule → [{number, title}]


# ---------------------------------------------------------------------------
# gh CLI helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("gh CLI not found")


def _search_issues(repo: str, query: str) -> List[Dict[str, Any]]:
    raw = _run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--search",
            query,
            "--state",
            "open",
            "--json",
            "number,title",
            "--limit",
            "5",
        ]
    )
    if not raw:
        return []
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return []


def _first_words(text: str, n: int = 5) -> str:
    return " ".join(text.split()[:n])


# ---------------------------------------------------------------------------
# IssueLinker
# ---------------------------------------------------------------------------


class IssueLinker:
    """Enriches BLOCKER/WARNING findings with links to related open issues."""

    def run(self, inp: LinkerInput) -> LinkedResult:
        enriched: List[Finding] = []
        related: Dict[str, List[Dict[str, Any]]] = {}

        for finding in inp.findings:
            if finding.severity not in (
                FindingSeverity.BLOCKER,
                FindingSeverity.WARNING,
            ):
                # SUGGESTION findings are skipped unchanged
                enriched.append(finding)
                continue

            query = f"{finding.rule} {_first_words(finding.message)}"
            try:
                matches = _search_issues(inp.repo, query)
            except RuntimeError as exc:
                logger.warning("IssueLinker: gh search failed — %s", exc)
                matches = []

            if matches:
                related[finding.rule] = matches
                see_also = ", ".join(
                    f"See also: #{m['number']} — {m['title']}" for m in matches
                )
                new_message = f"{finding.message} ({see_also})"
                enriched.append(finding.copy(update={"message": new_message}))
            else:
                enriched.append(finding)

        return LinkedResult(findings=enriched, related_issues=related)
