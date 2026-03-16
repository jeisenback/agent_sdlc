"""Unit tests for IssueLinker.

All gh CLI calls are mocked via unittest.mock — zero network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from agent_sdlc.agents.issue_linker import IssueLinker, LinkerInput
from agent_sdlc.core.findings import Finding, FindingSeverity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_run(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def _blocker(rule: str = "biz:missing-ac", msg: str = "Title is too vague") -> Finding:
    return Finding(
        severity=FindingSeverity.BLOCKER,
        rule=rule,
        message=msg,
        location="issue body",
    )


def _warning(
    rule: str = "DoR:no-description", msg: str = "Description is empty"
) -> Finding:
    return Finding(
        severity=FindingSeverity.WARNING,
        rule=rule,
        message=msg,
        location="issue body",
    )


def _suggestion(
    rule: str = "biz:add-label", msg: str = "Consider adding labels"
) -> Finding:
    return Finding(
        severity=FindingSeverity.SUGGESTION,
        rule=rule,
        message=msg,
        location="(unspecified)",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_blocker_finding_with_two_related_issues_appends_see_also():
    matches = [
        {"number": 10, "title": "Similar blocker A"},
        {"number": 11, "title": "Similar blocker B"},
    ]
    with patch("subprocess.run", return_value=_mock_run(json.dumps(matches))):
        result = IssueLinker().run(
            LinkerInput(findings=[_blocker()], repo="owner/repo")
        )

    assert len(result.findings) == 1
    msg = result.findings[0].message
    assert "See also: #10" in msg
    assert "See also: #11" in msg


def test_blocker_finding_with_two_related_issues_populates_related_issues():
    matches = [
        {"number": 10, "title": "Similar blocker A"},
        {"number": 11, "title": "Similar blocker B"},
    ]
    with patch("subprocess.run", return_value=_mock_run(json.dumps(matches))):
        result = IssueLinker().run(
            LinkerInput(findings=[_blocker()], repo="owner/repo")
        )

    assert "biz:missing-ac" in result.related_issues
    assert len(result.related_issues["biz:missing-ac"]) == 2


def test_suggestion_finding_is_not_searched():
    finding = _suggestion()
    with patch("subprocess.run") as mock_sp:
        result = IssueLinker().run(LinkerInput(findings=[finding], repo="owner/repo"))

    mock_sp.assert_not_called()
    assert result.findings[0].message == finding.message
    assert result.related_issues == {}


def test_gh_returns_empty_list_finding_unchanged():
    finding = _blocker(msg="Some blocker message")
    with patch("subprocess.run", return_value=_mock_run("[]")):
        result = IssueLinker().run(LinkerInput(findings=[finding], repo="owner/repo"))

    assert result.findings[0].message == finding.message
    assert result.related_issues == {}


def test_warning_finding_with_match_appends_see_also():
    matches = [{"number": 7, "title": "Related warning"}]
    with patch("subprocess.run", return_value=_mock_run(json.dumps(matches))):
        result = IssueLinker().run(
            LinkerInput(findings=[_warning()], repo="owner/repo")
        )

    assert "See also: #7" in result.findings[0].message


def test_mixed_findings_only_blocker_warning_searched():
    blocker = _blocker()
    suggestion = _suggestion()

    matches_blocker = [{"number": 3, "title": "A related issue"}]

    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        return _mock_run(json.dumps(matches_blocker))

    with patch("subprocess.run", side_effect=fake_run):
        result = IssueLinker().run(
            LinkerInput(findings=[blocker, suggestion], repo="owner/repo")
        )

    assert call_count == 1  # only the BLOCKER triggered a search
    assert "See also" in result.findings[0].message
    assert result.findings[1].message == suggestion.message


def test_gh_not_found_logs_warning_finding_unchanged():
    finding = _blocker()
    with patch("subprocess.run", side_effect=FileNotFoundError("gh not found")):
        result = IssueLinker().run(LinkerInput(findings=[finding], repo="owner/repo"))

    assert result.findings[0].message == finding.message
    assert result.related_issues == {}


def test_no_findings_returns_empty_result():
    result = IssueLinker().run(LinkerInput(findings=[], repo="owner/repo"))
    assert result.findings == []
    assert result.related_issues == {}


def test_severity_unchanged_after_enrichment():
    matches = [{"number": 1, "title": "Related"}]
    finding = _blocker()
    with patch("subprocess.run", return_value=_mock_run(json.dumps(matches))):
        result = IssueLinker().run(LinkerInput(findings=[finding], repo="owner/repo"))

    assert result.findings[0].severity == FindingSeverity.BLOCKER
