from agent_sdlc.agents.process_gap import ProcessGapAgent, ProcessGapInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def test_process_gap_approved_when_no_findings():
    provider = DummyLLMProvider(default="[]")
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(
        title="Add payment retry for card-network timeouts",
        description=(
            "As a customer (target user), I want payments to automatically retry "
            "on transient card-network timeouts so that checkout succeeds without me "
            "having to refresh. Success metric: checkout success rate ≥ 99.5%. "
            "Stakeholder: @pm-payments. Rollback: feature flag `payment_retry`."
        ),
    )
    res = agent.run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


def test_process_gap_blocker_no_why():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"biz:no-why",'
        '"message":"No business value stated","suggestion":"Add a why section"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(
        title="Add retry logic", description="The service sometimes fails."
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.blocker_count == 1
    assert res.findings[0].rule == "biz:no-why"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_process_gap_blocker_no_success_metric():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"biz:no-success-metric",'
        '"message":"No measurable outcome defined","suggestion":"Add a KPI or metric"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(title="Improve performance", description="Make it faster.")
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "biz:no-success-metric"


def test_process_gap_blocker_no_target_user():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"biz:no-target-user",'
        '"message":"No user persona identified","suggestion":"Add target user"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(title="New dashboard", description="Add a dashboard.")
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "biz:no-target-user"


def test_process_gap_warning_scope_creep():
    sample = (
        '[{"location":"description","severity":"warning","rule":"biz:scope-creep-risk",'
        '"message":"Multiple unrelated concerns","suggestion":"Split into separate issues"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(
        title="Fix auth and refactor DB", description="Fix auth bugs and refactor DB."
    )
    res = agent.run(inp)
    assert res.approved is True  # warnings don't block
    assert res.warning_count == 1
    assert res.findings[0].rule == "biz:scope-creep-risk"


def test_process_gap_suggestion_no_rollback():
    sample = (
        '[{"location":"description","severity":"suggestion","rule":"biz:no-rollback-plan",'
        '"message":"No rollback plan mentioned","suggestion":"Add rollback steps"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(title="Deploy new feature", description="Deploy it.")
    res = agent.run(inp)
    assert res.approved is True
    assert res.suggestion_count == 1
    assert res.findings[0].rule == "biz:no-rollback-plan"


def test_process_gap_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"description","severity":"suggestion","rule":"biz:no-rollback-plan","message":"No rollback"},'
        '{"location":"description","severity":"blocker","rule":"biz:no-why","message":"No why"},'
        '{"location":"description","severity":"warning","rule":"biz:scope-creep-risk","message":"Scope creep"}'
        "]"
    )
    provider = DummyLLMProvider(default=sample)
    agent = ProcessGapAgent(provider)
    inp = ProcessGapInput(title="Issue", description="desc")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_process_gap_default_mode_is_issue():
    inp = ProcessGapInput(title="t", description="d")
    assert inp.mode == "issue"
