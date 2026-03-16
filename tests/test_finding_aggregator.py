from agent_sdlc.agents.finding_aggregator import (
    AggregatorInput,
    FindingAggregator,
    _is_duplicate,
    _similarity,
)
from agent_sdlc.core.findings import Finding, FindingSeverity


def _f(
    rule: str,
    message: str,
    severity: FindingSeverity = FindingSeverity.WARNING,
    location: str = "file.py",
) -> Finding:
    return Finding(rule=rule, message=message, severity=severity, location=location)


def _agg() -> FindingAggregator:
    return FindingAggregator()


# ---------------------------------------------------------------------------
# Empty / single-agent
# ---------------------------------------------------------------------------


def test_empty_input_approved():
    inp = AggregatorInput(finding_sets=[])
    res = _agg().run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.by_agent == {}


def test_single_agent_no_findings():
    inp = AggregatorInput(finding_sets=[("AgentA", [])])
    res = _agg().run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.by_agent == {"AgentA": []}


def test_single_agent_with_findings():
    f1 = _f("DoR:ac-count", "No AC items", FindingSeverity.BLOCKER)
    f2 = _f("DoR:title", "Vague title", FindingSeverity.WARNING)
    inp = AggregatorInput(finding_sets=[("IssueAgent", [f1, f2])])
    res = _agg().run(inp)
    assert len(res.findings) == 2
    assert res.approved is False
    assert res.blocker_count == 1
    assert res.warning_count == 1
    assert "IssueAgent" in res.by_agent


# ---------------------------------------------------------------------------
# Approved / not approved
# ---------------------------------------------------------------------------


def test_approved_false_when_any_blocker():
    blocker = _f("code:type", "Missing types", FindingSeverity.BLOCKER)
    inp = AggregatorInput(finding_sets=[("PRAgent", [blocker])])
    res = _agg().run(inp)
    assert res.approved is False


def test_approved_true_when_only_warnings_and_suggestions():
    w = _f("DoR:size", "Too large", FindingSeverity.WARNING)
    s = _f("DoR:title", "Vague", FindingSeverity.SUGGESTION)
    inp = AggregatorInput(finding_sets=[("AgentA", [w, s])])
    res = _agg().run(inp)
    assert res.approved is True


# ---------------------------------------------------------------------------
# Deduplication — exact rule + location
# ---------------------------------------------------------------------------


def test_exact_duplicate_removed():
    f1 = _f("DoR:ac-count", "No AC", FindingSeverity.WARNING, "body")
    f2 = _f("DoR:ac-count", "Needs ACs", FindingSeverity.WARNING, "body")
    inp = AggregatorInput(finding_sets=[("A", [f1]), ("B", [f2])])
    res = _agg().run(inp)
    assert len(res.findings) == 1


def test_exact_duplicate_keeps_highest_severity():
    warning = _f("DoR:ac-count", "No AC", FindingSeverity.WARNING, "body")
    blocker = _f("DoR:ac-count", "No AC — blocker", FindingSeverity.BLOCKER, "body")
    inp = AggregatorInput(finding_sets=[("A", [warning]), ("B", [blocker])])
    res = _agg().run(inp)
    assert len(res.findings) == 1
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_different_locations_and_messages_not_deduplicated():
    f1 = _f(
        "DoR:ac-count",
        "Title is too vague and generic",
        FindingSeverity.WARNING,
        "title",
    )
    f2 = _f(
        "DoR:ac-count",
        "Body missing acceptance criteria checkboxes",
        FindingSeverity.WARNING,
        "body",
    )
    inp = AggregatorInput(finding_sets=[("A", [f1, f2])])
    res = _agg().run(inp)
    assert len(res.findings) == 2


# ---------------------------------------------------------------------------
# Deduplication — message similarity
# ---------------------------------------------------------------------------


def test_near_duplicate_message_removed():
    f1 = _f(
        "rule:a", "No acceptance criteria found in issue body", FindingSeverity.WARNING
    )
    f2 = _f(
        "rule:b", "No acceptance criteria found in issue body", FindingSeverity.WARNING
    )
    inp = AggregatorInput(finding_sets=[("A", [f1]), ("B", [f2])])
    res = _agg().run(inp)
    assert len(res.findings) == 1


def test_dissimilar_messages_both_kept():
    f1 = _f("rule:a", "Missing alt text on image element", FindingSeverity.WARNING)
    f2 = _f("rule:b", "No acceptance criteria in the issue", FindingSeverity.WARNING)
    inp = AggregatorInput(finding_sets=[("A", [f1]), ("B", [f2])])
    res = _agg().run(inp)
    assert len(res.findings) == 2


# ---------------------------------------------------------------------------
# Three agents with overlapping findings
# ---------------------------------------------------------------------------


def test_three_agents_overlap():
    shared = _f("DoR:ac-count", "No ACs", FindingSeverity.WARNING, "body")
    unique_a = _f(
        "biz:no-why", "No business value", FindingSeverity.BLOCKER, "description"
    )
    unique_b = _f("code:types", "Missing types", FindingSeverity.WARNING, "file.py")
    unique_c = _f("UI:alt-text", "Missing alt", FindingSeverity.BLOCKER, "index.html")

    inp = AggregatorInput(
        finding_sets=[
            ("IssueAgent", [shared, unique_a]),
            ("PRAgent", [shared, unique_b]),
            ("UIAgent", [unique_c]),
        ]
    )
    res = _agg().run(inp)
    # shared deduplicated to 1, plus 3 unique = 4
    assert len(res.findings) == 4
    assert res.approved is False
    assert res.blocker_count == 2
    assert set(res.by_agent.keys()) == {"IssueAgent", "PRAgent", "UIAgent"}


# ---------------------------------------------------------------------------
# Sort order
# ---------------------------------------------------------------------------


def test_findings_sorted_blocker_warning_suggestion():
    s = _f("r:s", "Suggestion", FindingSeverity.SUGGESTION)
    b = _f("r:b", "Blocker", FindingSeverity.BLOCKER)
    w = _f("r:w", "Warning", FindingSeverity.WARNING)
    inp = AggregatorInput(finding_sets=[("A", [s, b, w])])
    res = _agg().run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts():
    findings = [
        _f("r:b1", "b1", FindingSeverity.BLOCKER),
        _f("r:b2", "b2", FindingSeverity.BLOCKER, "other.py"),
        _f("r:w1", "w1", FindingSeverity.WARNING),
        _f("r:s1", "s1", FindingSeverity.SUGGESTION),
    ]
    inp = AggregatorInput(finding_sets=[("A", findings)])
    res = _agg().run(inp)
    assert res.blocker_count == 2
    assert res.warning_count == 1
    assert res.suggestion_count == 1


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------


def test_markdown_approved_contains_status():
    inp = AggregatorInput(finding_sets=[("A", [])])
    res = _agg().run(inp)
    md = _agg().to_markdown(res, pr_number=42)
    assert "PR #42" in md
    assert "No blockers" in md


def test_markdown_blocked_contains_status():
    b = _f("r:b", "Blocker msg", FindingSeverity.BLOCKER)
    inp = AggregatorInput(finding_sets=[("PRAgent", [b])])
    res = _agg().run(inp)
    md = _agg().to_markdown(res)
    assert "BLOCKED" in md
    assert "PRAgent" in md


def test_markdown_finding_row_present():
    w = _f("DoR:ac-count", "No AC items", FindingSeverity.WARNING, "body")
    inp = AggregatorInput(finding_sets=[("IssueAgent", [w])])
    res = _agg().run(inp)
    md = _agg().to_markdown(res, pr_number=1)
    assert "DoR:ac-count" in md
    assert "body" in md


# ---------------------------------------------------------------------------
# Similarity helper
# ---------------------------------------------------------------------------


def test_similarity_identical():
    assert _similarity("hello world", "hello world") == 1.0


def test_similarity_empty():
    assert _similarity("", "") == 1.0


def test_similarity_different():
    assert _similarity("abc", "xyz") < 0.5


def test_is_duplicate_exact_rule_location():
    f1 = _f("r:a", "msg one", location="loc")
    f2 = _f("r:a", "msg two", location="loc")
    assert _is_duplicate(f1, f2) is True


def test_is_duplicate_different_rule_and_location():
    f1 = _f("r:a", "completely different message alpha", location="loc1")
    f2 = _f("r:b", "nothing alike whatsoever beta gamma", location="loc2")
    assert _is_duplicate(f1, f2) is False
