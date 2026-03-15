from agent_sdlc.agents.process_gap import (
    ProcessGapAgent,
    ProcessGapInput,
    WorkflowGapInput,
)
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _agent(response: str = "[]") -> ProcessGapAgent:
    return ProcessGapAgent(DummyLLMProvider(default=response))


# ---------------------------------------------------------------------------
# Issue mode (existing tests, preserved)
# ---------------------------------------------------------------------------


def test_process_gap_approved_when_no_findings():
    agent = _agent("[]")
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
    agent = _agent(sample)
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
    agent = _agent(sample)
    inp = ProcessGapInput(title="Improve performance", description="Make it faster.")
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "biz:no-success-metric"


def test_process_gap_blocker_no_target_user():
    sample = (
        '[{"location":"description","severity":"blocker","rule":"biz:no-target-user",'
        '"message":"No user persona identified","suggestion":"Add target user"}]'
    )
    agent = _agent(sample)
    inp = ProcessGapInput(title="New dashboard", description="Add a dashboard.")
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "biz:no-target-user"


def test_process_gap_warning_scope_creep():
    sample = (
        '[{"location":"description","severity":"warning","rule":"biz:scope-creep-risk",'
        '"message":"Multiple unrelated concerns","suggestion":"Split into separate issues"}]'
    )
    agent = _agent(sample)
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
    agent = _agent(sample)
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
    agent = _agent(sample)
    inp = ProcessGapInput(title="Issue", description="desc")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_process_gap_default_mode_is_issue():
    inp = ProcessGapInput(title="t", description="d")
    assert inp.mode == "issue"


# ---------------------------------------------------------------------------
# Workflow mode tests
# ---------------------------------------------------------------------------

_MINIMAL_WORKFLOW_INP = WorkflowGapInput(
    claude_md="# CLAUDE.md\nSome content.",
    ci_workflows=[
        "# ci.yml\nname: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest"
    ],
)


def test_workflow_gap_approved_when_no_findings():
    agent = _agent("[]")
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.findings == []
    assert res.approved is True


def test_workflow_gap_blocker_no_dod():
    sample = (
        '[{"location":"CLAUDE.md","severity":"blocker","rule":"dev:no-dod",'
        '"message":"No Definition of Done found","suggestion":"Add DoD to CLAUDE.md"}]'
    )
    agent = _agent(sample)
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.approved is False
    assert res.findings[0].rule == "dev:no-dod"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_workflow_gap_blocker_no_deploy_smoke():
    sample = (
        '[{"location":"ci.yml","severity":"blocker","rule":"dev:no-deploy-smoke",'
        '"message":"No post-deploy smoke test step","suggestion":"Add a smoke test job"}]'
    )
    agent = _agent(sample)
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.approved is False
    assert res.findings[0].rule == "dev:no-deploy-smoke"


def test_workflow_gap_warning_no_changelog():
    sample = (
        '[{"location":"repo","severity":"warning","rule":"dev:no-changelog",'
        '"message":"No CHANGELOG found","suggestion":"Add CHANGELOG.md"}]'
    )
    agent = _agent(sample)
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.approved is True  # warnings don't block
    assert res.warning_count == 1
    assert res.findings[0].rule == "dev:no-changelog"


def test_workflow_gap_biz_warning_no_uat_gate():
    sample = (
        '[{"location":"CLAUDE.md","severity":"warning","rule":"biz:no-uat-gate",'
        '"message":"No UAT gate defined","suggestion":"Add UAT step to release process"}]'
    )
    agent = _agent(sample)
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.approved is True
    assert res.findings[0].rule == "biz:no-uat-gate"


def test_workflow_gap_default_mode_is_workflow():
    inp = WorkflowGapInput(claude_md="x", ci_workflows=[])
    assert inp.mode == "workflow"


def test_workflow_gap_optional_fields_default_none():
    inp = WorkflowGapInput(claude_md="x", ci_workflows=[])
    assert inp.codeowners is None
    assert inp.tasks_md is None
    assert inp.recent_pr_stats is None
    assert inp.issue_stats is None


def test_workflow_gap_findings_sorted():
    sample = (
        "["
        '{"location":"repo","severity":"suggestion","rule":"biz:no-release-comms","message":"No comms"},'
        '{"location":"ci.yml","severity":"blocker","rule":"dev:no-deploy-smoke","message":"No smoke"},'
        '{"location":"CLAUDE.md","severity":"warning","rule":"dev:no-changelog","message":"No changelog"}'
        "]"
    )
    agent = _agent(sample)
    res = agent.run(_MINIMAL_WORKFLOW_INP)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION
