"""TraceabilityChecker — deterministic rule-based traceability chain checker.

Checks the chain: Requirement → Issue → PR → Test → Deploy tag.
Does NOT call an LLM — all rules are deterministic regex/pattern checks.
Data is collected via gh CLI (or pre-fetched and passed in).
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity

# Patterns that indicate a linked issue in a PR body
_ISSUE_LINK_RE = re.compile(
    r"(closes|fixes|resolves|refs|references)\s+#\d+",
    re.IGNORECASE,
)

# Patterns that indicate a requirements reference in an issue body
_REQUIREMENTS_RE = re.compile(
    r"(REQUIREMENTS\.md|##\s*Requirements)",
    re.IGNORECASE,
)

# Source files that require accompanying tests
_SOURCE_GLOB = re.compile(r"^agent_sdlc/")
_TEST_GLOB = re.compile(r"^tests/")


class TraceabilityInput(BaseModel):
    pr_number: Optional[int] = None
    issue_number: Optional[int] = None
    pr_body: Optional[str] = None
    issue_body: Optional[str] = None
    changed_files: List[str] = []
    test_files_changed: List[str] = []


class TraceabilityResult(BaseModel):
    findings: List[Finding]

    @property
    def passed(self) -> bool:
        """True when there are zero WARNING or BLOCKER findings."""
        return not any(
            f.severity in (FindingSeverity.BLOCKER, FindingSeverity.WARNING)
            for f in self.findings
        )

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION)


class TraceabilityChecker:
    """Deterministic traceability chain checker (no LLM).

    Checks: PR linked to issue, issue linked to requirements, source changes
    accompanied by test changes. Rules namespace: trace:

    passed=True when zero WARNING or BLOCKER findings are present.
    Testable offline by pre-populating TraceabilityInput fields directly.
    """

    def __init__(self, inp: TraceabilityInput) -> None:
        if inp.pr_number is None and inp.issue_number is None:
            raise ValueError("pr_number or issue_number required")
        self._inp = inp

    def run(self) -> TraceabilityResult:
        findings: List[Finding] = []
        inp = self._inp

        # trace:pr-no-issue — PR body has no linked issue
        if inp.pr_number is not None and inp.pr_body is not None:
            if not _ISSUE_LINK_RE.search(inp.pr_body):
                findings.append(
                    Finding(
                        location=f"PR #{inp.pr_number} body",
                        severity=FindingSeverity.WARNING,
                        rule="trace:pr-no-issue",
                        message=(
                            "PR body contains no linked issue "
                            "(expected 'Closes #N', 'Fixes #N', or 'Refs #N')."
                        ),
                        suggestion=(
                            "Add 'Closes #<issue-number>' to the PR description "
                            "so the issue is auto-closed on merge."
                        ),
                    )
                )

        # trace:issue-no-requirement — issue body has no requirements link
        if inp.issue_number is not None and inp.issue_body is not None:
            if not _REQUIREMENTS_RE.search(inp.issue_body):
                findings.append(
                    Finding(
                        location=f"Issue #{inp.issue_number} body",
                        severity=FindingSeverity.SUGGESTION,
                        rule="trace:issue-no-requirement",
                        message=(
                            "Issue body has no link to REQUIREMENTS.md or a "
                            "'## Requirements' section."
                        ),
                        suggestion=(
                            "Add a reference to REQUIREMENTS.md or include a "
                            "'## Requirements' section listing the acceptance criteria."
                        ),
                    )
                )

        # trace:pr-no-tests — source files changed but no test files changed
        if inp.pr_number is not None:
            source_changed = any(_SOURCE_GLOB.match(f) for f in inp.changed_files)
            tests_changed = bool(inp.test_files_changed) or any(
                _TEST_GLOB.match(f) for f in inp.changed_files
            )
            if source_changed and not tests_changed:
                findings.append(
                    Finding(
                        location=f"PR #{inp.pr_number} changed files",
                        severity=FindingSeverity.WARNING,
                        rule="trace:pr-no-tests",
                        message=(
                            "PR changes source files under agent_sdlc/ but no "
                            "test files were changed."
                        ),
                        suggestion=(
                            "Add or update tests in tests/ to cover the changed source."
                        ),
                    )
                )

        return TraceabilityResult(findings=findings)


__all__ = ["TraceabilityChecker", "TraceabilityInput", "TraceabilityResult"]
