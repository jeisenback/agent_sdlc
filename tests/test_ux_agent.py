import pytest

from agent_sdlc.agents.ux import UXAgent, UXInput, UXResult
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _agent(response: str = "[]") -> UXAgent:
    return UXAgent(DummyLLMProvider(default=response))


def _inp(**kwargs) -> UXInput:  # type: ignore[no-untyped-def]
    defaults = dict(
        flow_description="1. User clicks Buy. 2. Order confirmed.",
        user_goal="Purchase a product",
    )
    defaults.update(kwargs)
    return UXInput(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_ux_approved_when_no_findings():
    res = _agent("[]").run(_inp())
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


# ---------------------------------------------------------------------------
# BLOCKER rules
# ---------------------------------------------------------------------------


def test_ux_blocker_no_error_state():
    sample = (
        '[{"location":"flow","severity":"blocker","rule":"UX:no-error-state",'
        '"message":"No error path described","suggestion":"Add error handling step"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is False
    assert res.blocker_count == 1
    f = res.findings[0]
    assert f.rule == "UX:no-error-state"
    assert f.severity == FindingSeverity.BLOCKER


def test_ux_blocker_no_success_feedback():
    sample = (
        '[{"location":"step 4","severity":"blocker","rule":"UX:no-success-feedback",'
        '"message":"Flow ends with no confirmation","suggestion":"Add success message"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is False
    f = res.findings[0]
    assert f.rule == "UX:no-success-feedback"
    assert f.severity == FindingSeverity.BLOCKER


def test_ux_blocker_dead_end():
    sample = (
        '[{"location":"step 3","severity":"blocker","rule":"UX:dead-end",'
        '"message":"Terminal state with no next action","suggestion":"Add recovery route"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is False
    f = res.findings[0]
    assert f.rule == "UX:dead-end"
    assert f.severity == FindingSeverity.BLOCKER


# ---------------------------------------------------------------------------
# WARNING rules
# ---------------------------------------------------------------------------


def test_ux_warning_step_count_high():
    sample = (
        '[{"location":"flow","severity":"warning","rule":"UX:step-count-high",'
        '"message":"8 steps before goal completion","suggestion":"Reduce to 5 or fewer"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is True  # warnings don't block
    assert res.warning_count == 1
    assert res.findings[0].rule == "UX:step-count-high"


def test_ux_warning_ambiguous_cta():
    sample = (
        '[{"location":"step 2","severity":"warning","rule":"UX:ambiguous-cta",'
        '"message":"CTA label is Submit with no outcome implied",'
        '"suggestion":"Use Place Order or Complete Purchase"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is True
    assert res.findings[0].rule == "UX:ambiguous-cta"


def test_ux_warning_undo_missing():
    sample = (
        '[{"location":"step 5","severity":"warning","rule":"UX:undo-missing",'
        '"message":"Delete action has no confirmation","suggestion":"Add confirmation dialog"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is True
    assert res.findings[0].rule == "UX:undo-missing"


# ---------------------------------------------------------------------------
# SUGGESTION rules
# ---------------------------------------------------------------------------


def test_ux_suggestion_loading_unaddressed():
    sample = (
        '[{"location":"step 3","severity":"suggestion","rule":"UX:loading-unaddressed",'
        '"message":"No loading indicator for payment processing","suggestion":"Add spinner"}]'
    )
    res = _agent(sample).run(_inp())
    assert res.approved is True
    assert res.suggestion_count == 1
    assert res.findings[0].rule == "UX:loading-unaddressed"


def test_ux_suggestion_mobile_friction():
    sample = (
        '[{"location":"step 2","severity":"suggestion","rule":"UX:mobile-friction",'
        '"message":"Hover tooltip not accessible on mobile","suggestion":"Use tap-friendly alternative"}]'
    )
    res = _agent(sample).run(_inp(user_type="mobile user"))
    assert res.approved is True
    assert res.findings[0].rule == "UX:mobile-friction"


# ---------------------------------------------------------------------------
# Sort order and counts
# ---------------------------------------------------------------------------


def test_ux_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"f","severity":"suggestion","rule":"UX:loading-unaddressed","message":"a"},'
        '{"location":"f","severity":"blocker","rule":"UX:no-error-state","message":"b"},'
        '{"location":"f","severity":"warning","rule":"UX:step-count-high","message":"c"}'
        "]"
    )
    res = _agent(sample).run(_inp())
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_ux_counts():
    sample = (
        "["
        '{"location":"f","severity":"blocker","rule":"UX:no-error-state","message":"a"},'
        '{"location":"f","severity":"blocker","rule":"UX:dead-end","message":"b"},'
        '{"location":"f","severity":"warning","rule":"UX:ambiguous-cta","message":"c"},'
        '{"location":"f","severity":"suggestion","rule":"UX:loading-unaddressed","message":"d"}'
        "]"
    )
    res = _agent(sample).run(_inp())
    assert res.blocker_count == 2
    assert res.warning_count == 1
    assert res.suggestion_count == 1
    assert res.approved is False


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


def test_ux_input_optional_fields_default_none():
    inp = UXInput(flow_description="flow", user_goal="goal")
    assert inp.user_type is None
    assert inp.flow_context is None


# ---------------------------------------------------------------------------
# Integration test stub (skipped without API key)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_ux_agent_integration_real_llm() -> None:
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    from agent_sdlc.core.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    agent = UXAgent(provider)
    inp = UXInput(
        flow_description=(
            "1. User clicks Delete Account.\n" "2. Account is deleted immediately."
        ),
        user_goal="Delete user account",
    )
    result = agent.run(inp)
    assert isinstance(result, UXResult)
    # Expect at least undo-missing warning for immediate delete
    rules = [f.rule for f in result.findings]
    assert any("undo" in r or "error" in r or "feedback" in r for r in rules)
