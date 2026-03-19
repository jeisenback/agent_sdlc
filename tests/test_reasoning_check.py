"""Tests for ReasoningCheckAgent — verifies BLOCKER findings before they block work."""

from agent_sdlc.agents.reasoning_check import (
    ReasoningCheckAgent,
    ReasoningCheckInput,
)
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _make_finding(
    rule: str = "test:rule",
    severity: FindingSeverity = FindingSeverity.BLOCKER,
    message: str = "A detailed finding message here.",
    suggestion: str = "Fix it this way.",
    location: str = "file.py",
) -> Finding:
    return Finding(
        rule=rule, severity=severity, message=message,
        suggestion=suggestion, location=location,
    )


# ---------------------------------------------------------------------------
# Deterministic mode (no provider)
# ---------------------------------------------------------------------------


def test_no_upstream_findings():
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="some diff")
    result = agent.run(inp)
    assert result.findings == []
    assert result.verified_findings == []
    assert result.approved is True


def test_good_blocker_passes_verification():
    f = _make_finding(
        rule="code:bad",
        severity=FindingSeverity.BLOCKER,
        message="Direct SDK import detected in agent.",
        suggestion="Use ProviderProtocol instead.",
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert f in result.verified_findings
    assert result.downgraded_findings == []
    assert result.approved is True  # no Reason: blocker findings


def test_blocker_with_no_suggestion_downgraded():
    f = _make_finding(
        rule="code:vague",
        severity=FindingSeverity.BLOCKER,
        message="Something is wrong with this code.",
        suggestion=None,
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert len(result.downgraded_findings) == 1
    assert result.downgraded_findings[0].severity == FindingSeverity.WARNING
    assert any("Reason:quality-issue" == fi.rule for fi in result.findings)


def test_blocker_with_short_message_downgraded():
    f = _make_finding(
        rule="code:x",
        severity=FindingSeverity.BLOCKER,
        message="bad",  # < 10 chars
        suggestion="fix it",
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert len(result.downgraded_findings) == 1


def test_blocker_with_generic_rule_downgraded():
    f = _make_finding(
        rule="general",
        severity=FindingSeverity.BLOCKER,
        message="This finding has a very generic rule ID.",
        suggestion="Add a namespace.",
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert len(result.downgraded_findings) == 1


def test_warning_with_issues_stays_verified():
    """Non-BLOCKER findings with quality issues are still verified (not downgraded)."""
    f = _make_finding(
        rule="general",
        severity=FindingSeverity.WARNING,
        message="short",
        suggestion=None,
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert f in result.verified_findings
    assert result.downgraded_findings == []


def test_multiple_findings_mixed():
    good = _make_finding(
        rule="code:ok",
        message="A well-formed finding with detail.",
        suggestion="Consider refactoring.",
    )
    bad = _make_finding(
        rule="general",
        message="bad",
        suggestion=None,
    )
    agent = ReasoningCheckAgent()
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[good, bad])
    result = agent.run(inp)
    assert good in result.verified_findings
    assert len(result.downgraded_findings) == 1


# ---------------------------------------------------------------------------
# LLM mode (with DummyLLMProvider)
# ---------------------------------------------------------------------------


def test_llm_mode_with_no_issues():
    provider = DummyLLMProvider(default="[]")
    agent = ReasoningCheckAgent(provider=provider)
    f = _make_finding(
        rule="code:ok",
        message="A detailed, well-formed finding.",
        suggestion="Consider refactoring.",
    )
    inp = ReasoningCheckInput(artifact="some diff", upstream_findings=[f])
    result = agent.run(inp)
    assert result.approved is True


def test_llm_mode_flags_unsound_finding():
    llm_response = (
        '[{"location":"file.py","severity":"blocker","rule":"Reason:unsound",'
        '"message":"Finding logic does not hold.","suggestion":"Remove the finding."}]'
    )
    provider = DummyLLMProvider(default=llm_response)
    agent = ReasoningCheckAgent(provider=provider)
    f = _make_finding(
        rule="code:ok",
        message="A well-formed finding with detail.",
        suggestion="Fix it.",
    )
    inp = ReasoningCheckInput(artifact="diff", upstream_findings=[f])
    result = agent.run(inp)
    assert result.approved is False
    assert result.blocker_count >= 1
    assert any(fi.rule == "Reason:unsound" for fi in result.findings)
