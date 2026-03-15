from agent_sdlc.agents.product_owner import ProductOwnerAgent, ProductOwnerInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _agent(response: str = "[]") -> ProductOwnerAgent:
    return ProductOwnerAgent(DummyLLMProvider(default=response))


def test_product_owner_approved_when_no_findings():
    agent = _agent("[]")
    inp = ProductOwnerInput(
        title="Retry failed payments for card-network timeouts",
        description=(
            "As a customer, I want payments to retry on transient card-network timeouts "
            "so that checkout succeeds without manual intervention. "
            "Success metric: checkout success rate ≥ 99.5%."
        ),
        target_users="customers at checkout",
    )
    res = agent.run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


def test_product_owner_blocker_value_unclear():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"PO:value-unclear",'
        '"message":"No user benefit stated","suggestion":"Describe the outcome for the user"}]'
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(
        title="Refactor auth module", description="Rewrite the auth module."
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.blocker_count == 1
    assert res.findings[0].rule == "PO:value-unclear"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_product_owner_blocker_no_target_user():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"PO:no-target-user",'
        '"message":"No user persona identified","suggestion":"Add target user or segment"}]'
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(
        title="Add dark mode", description="Add dark mode to the app."
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "PO:no-target-user"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_product_owner_blocker_unmeasurable_success():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"PO:unmeasurable-success",'
        '"message":"No KPI or metric defined","suggestion":"Add a measurable success criterion"}]'
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(
        title="Improve onboarding", description="Make the onboarding better."
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "PO:unmeasurable-success"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_product_owner_warning_scope_creep():
    sample = (
        '[{"location":"description","severity":"warning","rule":"PO:scope-creep",'
        '"message":"Multiple distinct problems addressed","suggestion":"Split into separate issues"}]'
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(
        title="Fix auth and rebuild search",
        description="Fix auth bugs and rebuild the search index.",
    )
    res = agent.run(inp)
    assert res.approved is True  # warnings don't block
    assert res.warning_count == 1
    assert res.findings[0].rule == "PO:scope-creep"


def test_product_owner_suggestion_ux_neglected():
    sample = (
        '[{"location":"description","severity":"suggestion","rule":"PO:ux-neglected",'
        '"message":"No UX consideration","suggestion":"Describe user-facing interaction"}]'
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(
        title="Optimise DB query", description="Add an index to the users table."
    )
    res = agent.run(inp)
    assert res.approved is True
    assert res.suggestion_count == 1
    assert res.findings[0].rule == "PO:ux-neglected"


def test_product_owner_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"description","severity":"suggestion","rule":"PO:ux-neglected","message":"No UX"},'
        '{"location":"title","severity":"blocker","rule":"PO:value-unclear","message":"No value"},'
        '{"location":"description","severity":"warning","rule":"PO:scope-creep","message":"Scope creep"}'
        "]"
    )
    agent = _agent(sample)
    inp = ProductOwnerInput(title="Issue", description="desc")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_product_owner_optional_context_fields():
    inp = ProductOwnerInput(title="t", description="d")
    assert inp.product_goals is None
    assert inp.target_users is None
    assert inp.existing_features is None
