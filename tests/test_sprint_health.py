"""Unit tests for SprintHealthReporter.

All gh CLI calls are mocked via unittest.mock — zero network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scripts.run_sprint_health import (
    build_report,
    collect_milestone_rows,
    fetch_blocked_issues,
    fetch_milestones,
    fetch_open_issues,
    identify_stale,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_run(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def _iso(days_ago: int) -> str:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# fetch_milestones
# ---------------------------------------------------------------------------


def test_fetch_milestones_parses_json():
    ms = {"number": 1, "title": "Sprint 1", "open_issues": 3, "closed_issues": 5}
    with patch("subprocess.run", return_value=_mock_run(json.dumps(ms))):
        result = fetch_milestones("owner/repo")
    assert len(result) == 1
    assert result[0]["title"] == "Sprint 1"


def test_fetch_milestones_empty_response():
    with patch("subprocess.run", return_value=_mock_run("")):
        result = fetch_milestones("owner/repo")
    assert result == []


# ---------------------------------------------------------------------------
# fetch_blocked_issues
# ---------------------------------------------------------------------------


def test_fetch_blocked_issues_returns_list():
    payload = json.dumps([{"number": 5, "title": "Blocked issue"}])
    with patch("subprocess.run", return_value=_mock_run(payload)):
        result = fetch_blocked_issues("owner/repo", "Sprint 1")
    assert len(result) == 1
    assert result[0]["number"] == 5


def test_fetch_blocked_issues_empty():
    with patch("subprocess.run", return_value=_mock_run("[]")):
        result = fetch_blocked_issues("owner/repo", "Sprint 1")
    assert result == []


# ---------------------------------------------------------------------------
# fetch_open_issues
# ---------------------------------------------------------------------------


def test_fetch_open_issues_returns_list():
    payload = json.dumps(
        [
            {"number": 1, "title": "Open issue", "updatedAt": _iso(1)},
        ]
    )
    with patch("subprocess.run", return_value=_mock_run(payload)):
        result = fetch_open_issues("owner/repo", "Sprint 1")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# identify_stale
# ---------------------------------------------------------------------------


def test_identify_stale_returns_old_issues():
    issues = [
        {"number": 1, "title": "Old issue", "updatedAt": _iso(10)},
        {"number": 2, "title": "Recent issue", "updatedAt": _iso(2)},
    ]
    stale = identify_stale(issues, stale_days=7)
    assert len(stale) == 1
    assert stale[0]["number"] == 1


def test_identify_stale_none_when_all_recent():
    issues = [
        {"number": 1, "title": "Fresh", "updatedAt": _iso(1)},
        {"number": 2, "title": "Also fresh", "updatedAt": _iso(3)},
    ]
    stale = identify_stale(issues, stale_days=7)
    assert stale == []


def test_identify_stale_all_stale():
    issues = [
        {"number": 1, "updatedAt": _iso(8)},
        {"number": 2, "updatedAt": _iso(30)},
    ]
    stale = identify_stale(issues, stale_days=7)
    assert len(stale) == 2


def test_identify_stale_skips_missing_updated_at():
    issues = [{"number": 1, "title": "No date", "updatedAt": ""}]
    stale = identify_stale(issues)
    assert stale == []


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


def test_build_report_no_blockers_no_tag():
    rows = [
        {
            "name": "Sprint 1",
            "total": 10,
            "pct_complete": 50,
            "blocker_count": 0,
            "stale_count": 1,
        }
    ]
    report = build_report(rows, "2026-01-01 09:00 UTC", owner="alice")
    assert "Sprint 1" in report
    assert "50%" in report
    assert "@alice" not in report  # no blockers > 2


def test_build_report_many_blockers_tags_owner():
    rows = [
        {
            "name": "Sprint 2",
            "total": 20,
            "pct_complete": 30,
            "blocker_count": 3,
            "stale_count": 2,
        }
    ]
    report = build_report(rows, "2026-01-01 09:00 UTC", owner="alice")
    assert "@alice" in report
    assert "Sprint 2" in report


def test_build_report_many_blockers_no_owner_fallback():
    rows = [
        {
            "name": "Sprint 2",
            "total": 20,
            "pct_complete": 30,
            "blocker_count": 3,
            "stale_count": 0,
        }
    ]
    report = build_report(rows, "2026-01-01 09:00 UTC", owner=None)
    assert "the team" in report


def test_build_report_zero_total_zero_percent():
    rows = [
        {
            "name": "Empty Sprint",
            "total": 0,
            "pct_complete": 0,
            "blocker_count": 0,
            "stale_count": 0,
        }
    ]
    report = build_report(rows, "2026-01-01 09:00 UTC")
    assert "0%" in report


def test_build_report_multiple_milestones():
    rows = [
        {
            "name": "Sprint 1",
            "total": 10,
            "pct_complete": 80,
            "blocker_count": 0,
            "stale_count": 0,
        },
        {
            "name": "Sprint 2",
            "total": 5,
            "pct_complete": 20,
            "blocker_count": 1,
            "stale_count": 3,
        },
    ]
    report = build_report(rows, "2026-01-01")
    assert "Sprint 1" in report
    assert "Sprint 2" in report
    assert "80%" in report
    assert "20%" in report


# ---------------------------------------------------------------------------
# collect_milestone_rows (integration of fetchers)
# ---------------------------------------------------------------------------


def test_collect_milestone_rows_one_milestone_no_blockers():
    milestones = [{"title": "Sprint 1", "open_issues": 5, "closed_issues": 5}]
    open_issues_payload = json.dumps(
        [
            {"number": 1, "title": "Issue 1", "updatedAt": _iso(1)},
        ]
    )
    blocked_payload = json.dumps([])

    call_count = 0

    def fake_run(cmd, **kwargs):
        nonlocal call_count
        call_count += 1
        if "--label" in cmd and "blocked" in cmd:
            return _mock_run(blocked_payload)
        if "--json" in cmd and "updatedAt" in cmd:
            return _mock_run(open_issues_payload)
        return _mock_run("[]")

    with patch("subprocess.run", side_effect=fake_run):
        rows = collect_milestone_rows("owner/repo", milestones)

    assert len(rows) == 1
    assert rows[0]["name"] == "Sprint 1"
    assert rows[0]["total"] == 10
    assert rows[0]["pct_complete"] == 50
    assert rows[0]["blocker_count"] == 0


def test_collect_milestone_rows_three_blockers():
    milestones = [{"title": "Sprint 2", "open_issues": 8, "closed_issues": 2}]
    blocked_payload = json.dumps(
        [
            {"number": 1, "title": "Blocked A"},
            {"number": 2, "title": "Blocked B"},
            {"number": 3, "title": "Blocked C"},
        ]
    )

    def fake_run(cmd, **kwargs):
        if "--label" in cmd and "blocked" in cmd:
            return _mock_run(blocked_payload)
        return _mock_run("[]")

    with patch("subprocess.run", side_effect=fake_run):
        rows = collect_milestone_rows("owner/repo", milestones)

    assert rows[0]["blocker_count"] == 3
    # build_report should include tag
    report = build_report(rows, "2026-01-01", owner="bob")
    assert "@bob" in report
