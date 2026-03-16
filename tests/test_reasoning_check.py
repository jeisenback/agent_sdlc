"""Unit tests for ReasoningCheckAgent (Sprint 2 scaffold).

All LLM calls use DummyLLMProvider — zero network calls.
"""

from __future__ import annotations

from agent_sdlc.agents.reasoning_check import (
    ReasoningCheckAgent,
    ReasoningCheckInput,
)
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocker(
    rule: str = "biz:missing-ac", msg: str = "AC missing", loc: str = "body"
) -> Finding:
    return Finding(
        severity=FindingSeverity.BLOCKER, rule=rule, message=msg, location=loc
    )


def _warning(rule: str = "biz:vague", msg: str = "Title vague") -> Finding:
    return Finding(
        severity=FindingSeverity.WARNING, rule=rule, message=msg, location="title"
    )


def _run(findings, trigger="blocker", response="keep"):
    """Run agent with DummyLLMProvider returning canned JSON."""
    canned = f'{{"action": "{response}", "reason": "test", "rule": "Reason:unsupported-blocker"}}'
    provider = DummyLLMProvider(default=canned)
    agent = ReasoningCheckAgent(provider=provider)
    return agent.run(
        ReasoningCheckInput(
            artifact="some artifact text",
            artifact_type="issue",
            upstream_agent="issue_refinement",
            findings=findings,
            trigger_reason=trigger,
        )
    )


# ---------------------------------------------------------------------------
# AC 1: canned JSON with Reason:unsupported-blocker → approved == False
# ---------------------------------------------------------------------------


def test_unsupported_blocker_finding_not_approved():
    """LLM says 'keep' on BLOCKER → verified_findings has BLOCKER → approved False."""
    result = _run([_blocker()], response="keep")
    assert result.approved is False
    assert len(result.verified_findings) == 1
    assert result.verified_findings[0].severity == FindingSeverity.BLOCKER


# ---------------------------------------------------------------------------
# AC 2: canned JSON with no BLOCKERs → approved == True
# ---------------------------------------------------------------------------


def test_no_blockers_in_input_is_approved():
    result = _run([_warning()])
    assert result.approved is True
    assert len(result.verified_findings) == 1


def test_blocker_removed_by_llm_gives_approved():
    """LLM removes the BLOCKER → no BLOCKERs remain → approved True."""
    result = _run([_blocker()], response="remove")
    assert result.approved is True
    assert len(result.removed) == 1
    assert len(result.verified_findings) == 0


def test_blocker_downgraded_by_llm_gives_approved():
    """LLM downgrades BLOCKER to WARNING → approved True."""
    result = _run([_blocker()], response="downgrade")
    assert result.approved is True
    assert len(result.downgraded) == 1
    assert result.downgraded[0].severity == FindingSeverity.WARNING


# ---------------------------------------------------------------------------
# AC 3: trigger_reason=miscommunication → contradiction logged (no crash)
# ---------------------------------------------------------------------------


def test_miscommunication_trigger_with_contradicting_blockers_does_not_crash():
    """Two BLOCKERs at the same location with different rules → logged, no crash."""
    f1 = _blocker(rule="biz:rule-a", loc="body")
    f2 = _blocker(rule="biz:rule-b", loc="body")
    result = _run([f1, f2], trigger="miscommunication", response="keep")
    # Both blockers still present since LLM said "keep"
    assert result.approved is False
    assert len(result.verified_findings) == 2


def test_miscommunication_no_contradictions_no_crash():
    """Miscomm trigger with no contradictions — logs nothing, proceeds normally."""
    result = _run([_warning()], trigger="miscommunication")
    assert result.approved is True


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_empty_findings_returns_approved():
    result = _run([])
    assert result.approved is True
    assert result.verified_findings == []
    assert result.downgraded == []
    assert result.removed == []


def test_non_blockers_pass_through_unchanged():
    w = _warning()
    result = _run([w], response="keep")
    assert result.approved is True
    assert any(f.rule == w.rule for f in result.verified_findings)


def test_provider_error_falls_back_to_keep():
    """If provider raises, finding is kept (not removed)."""
    from unittest.mock import MagicMock

    broken_provider = MagicMock()
    broken_provider.complete.side_effect = RuntimeError("network error")
    agent = ReasoningCheckAgent(provider=broken_provider)
    result = agent.run(
        ReasoningCheckInput(
            artifact="x",
            artifact_type="diff",
            upstream_agent="pr_review",
            findings=[_blocker()],
            trigger_reason="blocker",
        )
    )
    # Fallback: keep the finding
    assert len(result.verified_findings) == 1
    assert result.approved is False
