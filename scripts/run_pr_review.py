"""Simple runner for the PR review agent (local/demo only).

Usage: python scripts/run_pr_review.py
"""
from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.providers import DummyLLMProvider


def main() -> None:
    # Demo response: a JSON array acceptable to the PRReviewAgent
    demo_response = '[{"id":"1","title":"Use f-strings","description":"old-style formatting detected","severity":"LOW","tags":["style"]}]'
    provider = DummyLLMProvider(default=demo_response)
    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Example PR", diff="- x = '%s' % name\n+ x = f'{name}'")
    out = agent.run(inp)
    print(out.json(indent=2))


if __name__ == "__main__":
    main()
