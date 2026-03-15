from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def test_pr_review_no_findings():
    provider = DummyLLMProvider(default="[]")
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Clean PR", diff="+ pass")
    res = agent.run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


def test_pr_review_agent_parses_findings():
    sample = (
        '[{"location":"src/foo.py","severity":"warning","rule":"code:type-hints",'
        '"message":"Missing return type hint","suggestion":"Add -> None"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Add foo", diff="+ def bar(): pass")
    res = agent.run(inp)
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.severity == FindingSeverity.WARNING
    assert f.rule == "code:type-hints"
    assert res.approved is True  # no blockers
    assert res.warning_count == 1


def test_pr_review_blocker_fails_approval():
    sample = (
        '[{"location":"agent_sdlc/agents/foo.py","severity":"blocker",'
        '"rule":"code:no-direct-sdk","message":"Direct anthropic import detected",'
        '"suggestion":"Use ProviderProtocol instead"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Bad PR", diff="+ import anthropic")
    res = agent.run(inp)
    assert res.approved is False
    assert res.blocker_count == 1


def test_pr_review_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"a.py","severity":"suggestion","rule":"style","message":"minor"},'
        '{"location":"b.py","severity":"blocker","rule":"code:no-direct-sdk","message":"critical"}'
        "]"
    )
    provider = DummyLLMProvider(default=sample)
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Mixed", diff="+ x = 1")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.SUGGESTION
