from __future__ import annotations

from typing import List

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class IssueInput(BaseModel):
    title: str
    description: str


class IssueRefinementResult(BaseModel):
    findings: List[Finding]

    @property
    def ready(self) -> bool:
        """True only when there are zero BLOCKER findings."""
        return not any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION)


class IssueRefinementAgent:
    """Issue refinement agent that checks Definition of Ready via LLM.

    The agent expects the provider to return a JSON array matching the Finding
    model (fields: location, severity, rule, message, suggestion).
    Severity must be one of: blocker, warning, suggestion.

    ready=True when no BLOCKER findings are present — safe to enter a sprint.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: IssueInput) -> IssueRefinementResult:
        prompt = (
            f"Check this issue's Definition of Ready.\n"
            f"Issue title: '{inp.title}'\n"
            f"Return a JSON array of findings. Each item must have:\n"
            f"  location (str, e.g. 'body', 'title', 'labels'),\n"
            f"  severity (blocker|warning|suggestion),\n"
            f"  rule (str, e.g. 'DoR:ac-count'), message (str), suggestion (str or null).\n"
            f"Return [] if the issue is ready.\n"
            f"DESCRIPTION:\n{inp.description}\n"
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return IssueRefinementResult(findings=findings)


__all__ = ["IssueRefinementAgent", "IssueInput", "IssueRefinementResult"]
