from agent_sdlc.agents.issue_refinement import IssueRefinementAgent, IssueInput
from agent_sdlc.core.providers import DummyLLMProvider


def test_issue_refinement_parses_suggestions():
    sample = '[{"id":"s1","title":"Add repro steps","description":"Provide steps to reproduce","severity":"LOW","tags":["process"]}]'
    provider = DummyLLMProvider(default=sample)
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(title="Crash on save", description="Crashes when saving large files")
    res = agent.run(inp)
    assert len(res.suggestions) == 1
    s = res.suggestions[0]
    assert s.title == "Add repro steps"
