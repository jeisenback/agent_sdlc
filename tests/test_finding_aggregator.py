"""Tests for FindingAggregator — deterministic finding merging."""

from agent_sdlc.agents.finding_aggregator import (
    AgentFindings,
    AggregatorInput,
    AggregatorResult,
    FindingAggregator,
)
from agent_sdlc.core.findings import Finding, FindingSeverity


def _make_finding(
    rule: str = "test:rule",
    location: str = "file.py",
    severity: FindingSeverity = FindingSeverity.WARNING,
    message: str = "test message",
) -> Finding:
    return Finding(rule=rule, location=location, severity=severity, message=message)


def test_empty_input():
    agg = FindingAggregator()
    result = agg.run(AggregatorInput())
    assert result.findings == []
    assert result.approved is True
    assert result.blocker_count == 0


def test_single_agent_passthrough():
    findings = [_make_finding(rule="code:x", severity=FindingSeverity.WARNING)]
    inp = AggregatorInput(
        agent_findings=[AgentFindings(agent="pr_review", findings=findings)]
    )
    result = FindingAggregator().run(inp)
    assert len(result.findings) == 1
    assert result.findings[0].rule == "code:x"
    assert result.approved is True
    assert result.warning_count == 1


def test_dedup_same_rule_location_keeps_higher_severity():
    f1 = _make_finding(rule="code:x", location="a.py", severity=FindingSeverity.WARNING)
    f2 = _make_finding(rule="code:x", location="a.py", severity=FindingSeverity.BLOCKER)

    inp = AggregatorInput(
        agent_findings=[
            AgentFindings(agent="agent_a", findings=[f1]),
            AgentFindings(agent="agent_b", findings=[f2]),
        ]
    )
    result = FindingAggregator().run(inp)
    assert len(result.findings) == 1
    assert result.findings[0].severity == FindingSeverity.BLOCKER
    assert result.approved is False


def test_different_rules_not_deduped():
    f1 = _make_finding(rule="code:x", location="a.py")
    f2 = _make_finding(rule="code:y", location="a.py")

    inp = AggregatorInput(
        agent_findings=[AgentFindings(agent="agent_a", findings=[f1, f2])]
    )
    result = FindingAggregator().run(inp)
    assert len(result.findings) == 2


def test_different_locations_not_deduped():
    f1 = _make_finding(rule="code:x", location="a.py")
    f2 = _make_finding(rule="code:x", location="b.py")

    inp = AggregatorInput(
        agent_findings=[AgentFindings(agent="agent_a", findings=[f1, f2])]
    )
    result = FindingAggregator().run(inp)
    assert len(result.findings) == 2


def test_findings_sorted_blockers_first():
    f1 = _make_finding(rule="a:sug", severity=FindingSeverity.SUGGESTION)
    f2 = _make_finding(rule="b:blk", severity=FindingSeverity.BLOCKER)
    f3 = _make_finding(rule="c:wrn", severity=FindingSeverity.WARNING)

    inp = AggregatorInput(
        agent_findings=[AgentFindings(agent="x", findings=[f1, f2, f3])]
    )
    result = FindingAggregator().run(inp)
    assert result.findings[0].severity == FindingSeverity.BLOCKER
    assert result.findings[1].severity == FindingSeverity.WARNING
    assert result.findings[2].severity == FindingSeverity.SUGGESTION


def test_agents_ran_and_failed_tracked():
    inp = AggregatorInput(
        agent_findings=[
            AgentFindings(agent="ok_agent", findings=[], exit_code=0),
            AgentFindings(agent="bad_agent", findings=[], exit_code=1),
        ]
    )
    result = FindingAggregator().run(inp)
    assert result.agents_ran == ["ok_agent", "bad_agent"]
    assert result.agents_failed == ["bad_agent"]


def test_pipeline_run_id_passthrough():
    inp = AggregatorInput(
        pipeline_run_id="run-123",
        agent_findings=[AgentFindings(agent="a", findings=[])],
    )
    result = FindingAggregator().run(inp)
    assert result.pipeline_run_id == "run-123"


def test_blocker_finding_makes_approved_false():
    findings = [_make_finding(severity=FindingSeverity.BLOCKER)]
    inp = AggregatorInput(
        agent_findings=[AgentFindings(agent="a", findings=findings)]
    )
    result = FindingAggregator().run(inp)
    assert result.approved is False
    assert result.blocker_count == 1


def test_multiple_agents_merged():
    fa = [_make_finding(rule="a:1", location="x.py")]
    fb = [_make_finding(rule="b:1", location="y.py")]

    inp = AggregatorInput(
        agent_findings=[
            AgentFindings(agent="agent_a", findings=fa),
            AgentFindings(agent="agent_b", findings=fb),
        ]
    )
    result = FindingAggregator().run(inp)
    assert len(result.findings) == 2
    assert result.agents_ran == ["agent_a", "agent_b"]
