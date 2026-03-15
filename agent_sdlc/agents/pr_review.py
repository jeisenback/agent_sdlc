from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

from agent_sdlc.core.findings import Finding
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class PRReviewInput(BaseModel):
    title: str
    diff: str
    author: Optional[str] = None


class PRReviewResult(BaseModel):
    findings: List[Finding]


class PRReviewAgent:
    """Simple PR review agent that asks the LLM to return a JSON list of Findings.

    This agent expects the provider to return a JSON array matching the `Finding` model.
    The approach keeps the agent lightweight and easy to test with `DummyLLMProvider`.
    """

    def __init__(self, provider: ProviderProtocol):
        self.llm = LLMWrapper(provider)

    def run(self, inp: PRReviewInput) -> PRReviewResult:
        prompt = (
            f"Review the following pull request titled '{inp.title}'.\n"
            f"Return a JSON array of findings with fields (id,title,description,severity,tags).\n"
            f"DIFF:\n{inp.diff}\n"
        )
        text = self.llm.ask_text(prompt)
        # parse JSON in a way that's compatible with pydantic v1 and v2
        from agent_sdlc.core.findings import parse_findings_from_json

        findings = parse_findings_from_json(text)
        return PRReviewResult(findings=findings)


__all__ = ["PRReviewAgent", "PRReviewInput", "PRReviewResult"]
