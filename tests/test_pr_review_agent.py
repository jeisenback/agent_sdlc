from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.providers import DummyLLMProvider


def test_pr_review_agent_parses_findings():
    sample = '[{"id":"1","title":"Use f-strings","description":"old-style formatting detected","severity":"LOW","tags":["style"]}]'
    provider = DummyLLMProvider(default=sample)
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Add foo", diff="- x = '%s' % name\n+ x = f'{name}'")
    res = agent.run(inp)
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.title == "Use f-strings"
    assert f.severity.value == "LOW"
