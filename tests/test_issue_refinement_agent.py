from agent_sdlc.agents.issue_refinement import IssueInput, IssueRefinementAgent
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def test_issue_refinement_ready_when_no_findings():
    provider = DummyLLMProvider(default="[]")
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(
        title="Add retry logic", description="- [ ] impl\n- [ ] test\n- [ ] docs"
    )
    res = agent.run(inp)
    assert res.findings == []
    assert res.ready is True
    assert res.blocker_count == 0


def test_issue_refinement_parses_suggestions():
    sample = (
        '[{"location":"body","severity":"suggestion","rule":"DoR:ac-clarity",'
        '"message":"AC item is vague","suggestion":"Make it testable"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(
        title="Crash on save", description="Crashes when saving large files"
    )
    res = agent.run(inp)
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.severity == FindingSeverity.SUGGESTION
    assert f.rule == "DoR:ac-clarity"
    assert res.ready is True  # suggestions don't block


def test_issue_refinement_blocker_not_ready():
    sample = (
        '[{"location":"body","severity":"blocker","rule":"DoR:ac-count",'
        '"message":"Fewer than 3 AC checkboxes found","suggestion":"Add more - [ ] items"}]'
    )
    provider = DummyLLMProvider(default=sample)
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(title="Vague issue", description="Something is broken")
    res = agent.run(inp)
    assert res.ready is False
    assert res.blocker_count == 1


def test_issue_refinement_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"labels","severity":"warning","rule":"DoR:label-type","message":"No type label"},'
        '{"location":"body","severity":"blocker","rule":"DoR:ac-count","message":"No AC items"}'
        "]"
    )
    provider = DummyLLMProvider(default=sample)
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(title="Issue", description="desc")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
