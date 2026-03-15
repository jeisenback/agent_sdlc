from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

from agent_sdlc.core.findings import Finding
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class IssueInput(BaseModel):
    title: str
    description: str


class IssueRefinementResult(BaseModel):
    suggestions: List[Finding]


class IssueRefinementAgent:
    """Agent that asks the LLM to refine an issue into structured suggestions.

    The agent expects a JSON array of Finding-like suggestions from the provider.
    """

    def __init__(self, provider: ProviderProtocol):
        self.llm = LLMWrapper(provider)

    def run(self, inp: IssueInput) -> IssueRefinementResult:
        prompt = (
            f"Refine the issue titled '{inp.title}'. Return a JSON array of suggestions "
            f"(id,title,description,severity,tags).\nDESCRIPTION:\n{inp.description}\n"
        )
        text = self.llm.ask_text(prompt)
        # parse JSON in a way that's compatible with pydantic v1 and v2
        from agent_sdlc.core.findings import parse_findings_from_json

        suggestions = parse_findings_from_json(text)
        return IssueRefinementResult(suggestions=suggestions)


__all__ = [
    "IssueRefinementAgent",
    "IssueInput",
    "IssueRefinementResult",
]
