"""Example: run Issue Refinement agent locally with DummyLLMProvider."""

from agent_sdlc.agents.issue_refinement import IssueInput, IssueRefinementAgent
from agent_sdlc.core.providers import DummyLLMProvider


def main() -> None:
    demo_response = '[{"id":"s1","title":"Add repro steps","description":"Provide steps to reproduce","severity":"LOW","tags":["process"]}]'
    provider = DummyLLMProvider(default=demo_response)

    # To use a real provider (replace stub with real adapter):
    # from agent_sdlc.core.providers import AnthropicProvider
    # provider = AnthropicProvider(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    agent = IssueRefinementAgent(provider)
    inp = IssueInput(
        title="Crash on save", description="Crashes when saving large files"
    )
    out = agent.run(inp)
    print(out.json(indent=2))


if __name__ == "__main__":
    main()
