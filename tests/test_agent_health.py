"""Unit tests for AgentHealthMonitor.

All gh CLI calls are mocked via unittest.mock — zero network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from scripts.run_agent_health import analyse, build_report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_run(stdout: str) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = 0
    return m


def _closed_pr(number: int, closed_at: str = "2026-03-10T10:00:00Z") -> dict:
    return {
        "number": number,
        "title": f"PR #{number}",
        "closedAt": closed_at,
        "mergedAt": closed_at,
    }


def _comment_with_blocker(rule: str = "biz:missing-ac") -> dict:
    return {
        "body": f"[BLOCKER] {rule} @ issue body: Acceptance criteria missing",
        "created_at": "2026-03-10T11:00:00Z",
        "user": "bot",
    }


def _dismiss_comment() -> dict:
    return {
        "body": "wontfix — not relevant to this PR",
        "created_at": "2026-03-10T12:00:00Z",
        "user": "reviewer",
    }


# ---------------------------------------------------------------------------
# AC 1: 0 findings history → 0% coverage
# ---------------------------------------------------------------------------


def test_zero_findings_gives_zero_coverage():
    closed_prs = []  # no closed PRs

    def fake_run(cmd, **kwargs):
        if "pr" in cmd and "list" in cmd and "closed" in cmd:
            return _mock_run(json.dumps(closed_prs))
        if "pr" in cmd and "list" in cmd and "all" in cmd:
            return _mock_run(json.dumps([{"number": 5}, {"number": 6}]))
        return _mock_run("[]")

    with patch("subprocess.run", side_effect=fake_run):
        metrics = analyse("owner/repo", days=30)

    assert metrics["coverage_pct"] == 0
    assert metrics["prs_with_findings"] == 0


def test_zero_total_prs_gives_zero_coverage():
    def fake_run(cmd, **kwargs):
        return _mock_run("[]")

    with patch("subprocess.run", side_effect=fake_run):
        metrics = analyse("owner/repo", days=30)

    assert metrics["coverage_pct"] == 0


# ---------------------------------------------------------------------------
# AC 2: 2 of 4 BLOCKERs unresolved → 50% dismiss rate
# ---------------------------------------------------------------------------


def test_two_of_four_blockers_unresolved_is_50_percent_dismiss():
    """4 PRs each with one BLOCKER; 2 have dismiss comment → 50% dismiss rate."""
    rule = "biz:missing-ac"
    prs = [_closed_pr(i, "2026-03-10T10:00:00Z") for i in range(1, 5)]

    def fake_run(cmd, **kwargs):
        if "pr" in cmd and "list" in cmd and "closed" in cmd:
            return _mock_run(json.dumps(prs))
        if "pr" in cmd and "list" in cmd and "all" in cmd:
            return _mock_run(json.dumps([{"number": i} for i in range(1, 5)]))
        # API call for PR comments: gh api repos/.../issues/N/comments
        url = next((c for c in cmd if "issues/" in c and "comments" in c), "")
        if url:
            pr_num = int(url.split("issues/")[1].split("/")[0])
            # PRs 1 and 2 get dismiss comment; 3 and 4 don't
            if pr_num in (1, 2):
                return _mock_run(
                    "\n".join(
                        json.dumps(c)
                        for c in [_comment_with_blocker(rule), _dismiss_comment()]
                    )
                )
            else:
                return _mock_run(json.dumps(_comment_with_blocker(rule)))
        return _mock_run("[]")

    with patch("subprocess.run", side_effect=fake_run):
        metrics = analyse("owner/repo", days=30)

    dismiss_rates = metrics["dismiss_rates"]
    assert rule in dismiss_rates
    assert dismiss_rates[rule] == 50.0


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


def test_build_report_includes_coverage_and_top_rules():
    metrics = {
        "repo": "owner/repo",
        "period_days": 30,
        "coverage_pct": 75,
        "rule_fire_counts": {"biz:rule-a": 10, "biz:rule-b": 5},
        "dismiss_rates": {"biz:rule-a": 60.0, "biz:rule-b": 10.0},
        "top_fired_rules": [("biz:rule-a", 10), ("biz:rule-b", 5)],
        "top_dismiss_rate_rules": [("biz:rule-a", 60.0), ("biz:rule-b", 10.0)],
        "high_dismiss_rules": ["biz:rule-a"],
    }
    report = build_report(metrics, "2026-03-15 09:00 UTC")

    assert "75%" in report
    assert "biz:rule-a" in report
    assert "60.0%" in report
    assert "needs-prompt-review" in report


def test_build_report_no_high_dismiss():
    metrics = {
        "repo": "owner/repo",
        "period_days": 30,
        "coverage_pct": 50,
        "rule_fire_counts": {},
        "dismiss_rates": {},
        "top_fired_rules": [],
        "top_dismiss_rate_rules": [],
        "high_dismiss_rules": [],
    }
    report = build_report(metrics, "2026-03-15")
    assert "needs-prompt-review" not in report
    assert "50%" in report
