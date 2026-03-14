"""Simple runner for the Issue Refinement agent (local/demo only).

Usage: python scripts/run_issue_refinement.py
"""
from agent_sdlc.agents.issue_refinement import IssueRefinementAgent, IssueInput
from agent_sdlc.core.providers import DummyLLMProvider


def main() -> None:
    demo_response = '[{"id":"s1","title":"Add repro steps","description":"Ask for minimal repro steps","severity":"LOW","tags":["process"]}]'
    provider = DummyLLMProvider(default=demo_response)
    agent = IssueRefinementAgent(provider)
    inp = IssueInput(title="Bug: crash on save", description="App crashes when saving a file under certain conditions")
    out = agent.run(inp)
    print(out.json(indent=2))


if __name__ == "__main__":
    main()
