"""Unit tests for AgentConflictResolver.

DummyLLMProvider for semantic checks — zero network calls.
"""

from __future__ import annotations

import json

from agent_sdlc.agents.conflict_resolver import (
    AgentConflictResolver,
    ConflictInput,
)
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocker(rule="biz:missing-ac", msg="AC missing", loc="body"):
    return Finding(
        severity=FindingSeverity.BLOCKER, rule=rule, message=msg, location=loc
    )


def _warning(rule="biz:missing-ac", msg="AC missing", loc="body"):
    return Finding(
        severity=FindingSeverity.WARNING, rule=rule, message=msg, location=loc
    )


def _suggestion(rule="biz:add-label", msg="Add label", loc="labels"):
    return Finding(
        severity=FindingSeverity.SUGGESTION, rule=rule, message=msg, location=loc
    )


def _run(finding_sets, artifact="test artifact", llm_response="{}"):
    provider = DummyLLMProvider(default=llm_response)
    agent = AgentConflictResolver(provider=provider)
    return agent.run(ConflictInput(finding_sets=finding_sets, artifact=artifact))


# ---------------------------------------------------------------------------
# AC 1: same rule different severity → higher severity wins
# ---------------------------------------------------------------------------


def test_structural_conflict_higher_severity_wins():
    sets = [
        ("agent_a", [_blocker()]),  # BLOCKER
        ("agent_b", [_warning()]),  # WARNING — same rule, same location
    ]
    result = _run(sets)

    assert len(result.resolved_findings) == 1
    assert result.resolved_findings[0].severity == FindingSeverity.BLOCKER
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["type"] == "structural"


def test_structural_conflict_blocker_beats_suggestion():
    sets = [
        ("agent_a", [_blocker()]),
        ("agent_b", [_suggestion("biz:missing-ac", "AC missing", "body")]),
    ]
    result = _run(sets)
    assert result.resolved_findings[0].severity == FindingSeverity.BLOCKER


# ---------------------------------------------------------------------------
# AC 2: no conflict → pass-through unchanged
# ---------------------------------------------------------------------------


def test_no_conflict_passes_through():
    f1 = _blocker(rule="biz:rule-a", loc="title")
    f2 = _warning(rule="biz:rule-b", loc="body")
    sets = [("agent_a", [f1]), ("agent_b", [f2])]
    result = _run(sets)

    assert len(result.conflicts) == 0
    assert len(result.escalated) == 0
    rules = {f.rule for f in result.resolved_findings}
    assert "biz:rule-a" in rules
    assert "biz:rule-b" in rules


def test_empty_finding_sets():
    result = _run([])
    assert result.resolved_findings == []
    assert result.conflicts == []
    assert result.escalated == []


def test_single_agent_no_conflict():
    f = _blocker()
    result = _run([("agent_a", [f])])
    assert len(result.resolved_findings) == 1
    assert result.conflicts == []


# ---------------------------------------------------------------------------
# AC 3: escalation fires when LLM returns low-confidence verdict
# ---------------------------------------------------------------------------


def test_escalation_when_llm_low_confidence():
    low_conf = json.dumps(
        {
            "contradiction": True,
            "confidence": 0.4,  # below 0.7 threshold
            "winner": "A",
            "rationale": "Uncertain",
        }
    )
    f1 = _blocker(rule="biz:rule-x", msg="Problem X found", loc="body")
    f2 = _warning(rule="biz:rule-y", msg="Problem Y found", loc="body")
    sets = [("agent_a", [f1]), ("agent_b", [f2])]
    result = _run(sets, llm_response=low_conf)

    assert len(result.escalated) == 1
    assert result.escalated[0]["label"] == "needs-human-review"


def test_no_escalation_when_llm_high_confidence():
    high_conf = json.dumps(
        {
            "contradiction": True,
            "confidence": 0.9,
            "winner": "A",
            "rationale": "Finding A clearly more accurate",
        }
    )
    f1 = _blocker(rule="biz:rule-x", msg="Problem X found", loc="body")
    f2 = _warning(rule="biz:rule-y", msg="Problem Y found", loc="body")
    sets = [("agent_a", [f1]), ("agent_b", [f2])]
    result = _run(sets, llm_response=high_conf)

    assert len(result.escalated) == 0
    assert any(c["type"] == "semantic" for c in result.conflicts)


# ---------------------------------------------------------------------------
# Suggestions skipped in semantic check
# ---------------------------------------------------------------------------


def test_suggestion_findings_not_semantically_checked():
    """SUGGESTION findings pass through without LLM calls."""
    s1 = _suggestion()
    s2 = _suggestion(rule="biz:rule-2", msg="Other suggestion", loc="labels")
    result = _run([("a", [s1]), ("b", [s2])])
    # No semantic conflicts should be detected for suggestions
    assert len(result.escalated) == 0
    assert len(result.resolved_findings) == 2
