"""Example: run PR review agent locally with DummyLLMProvider.

Demonstrates swapping provider implementations by editing the provider
construction section.
"""

from agent_sdlc.agents.pr_review import PRReviewAgent, PRReviewInput
from agent_sdlc.core.providers import DummyLLMProvider


def main() -> None:
    # Deterministic demo response (JSON array of findings)
    demo_response = '[{"id":"1","title":"Use f-strings","description":"old-style formatting detected","severity":"LOW","tags":["style"]}]'
    provider = DummyLLMProvider(default=demo_response)

    # To use a real provider (replace stub with real adapter):
    # from agent_sdlc.core.providers import OpenAIProvider
    # provider = OpenAIProvider(api_key=os.environ.get("OPENAI_API_KEY"))

    agent = PRReviewAgent(provider)
    inp = PRReviewInput(title="Example PR", diff="- x = '%s' % name\n+ x = f'{name}'")
    out = agent.run(inp)
    print(out.json(indent=2))


if __name__ == "__main__":
    main()
