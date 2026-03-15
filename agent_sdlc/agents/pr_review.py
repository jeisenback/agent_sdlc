from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import (Finding, FindingSeverity,
                                      parse_findings_from_json)
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class PRReviewInput(BaseModel):
    title: str
    diff: str
    author: Optional[str] = None


class PRReviewResult(BaseModel):
    findings: List[Finding]

    @property
    def approved(self) -> bool:
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


class PRReviewAgent:
    """PR review agent that asks the LLM to return a JSON list of Findings.

    The agent expects the provider to return a JSON array matching the Finding
    model (fields: location, severity, rule, message, suggestion).
    Severity must be one of: blocker, warning, suggestion.

    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: PRReviewInput) -> PRReviewResult:
        prompt = (
            f"Review the following pull request titled '{inp.title}'.\n"
            f"Return a JSON array of findings. Each item must have:\n"
            f"  location (str), severity (blocker|warning|suggestion),\n"
            f"  rule (str), message (str), suggestion (str or null).\n"
            f"Exit 0 if no findings: return [].\n"
            f"DIFF:\n{inp.diff}\n"
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        # Sort: blockers first, then warnings, then suggestions
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return PRReviewResult(findings=findings)


__all__ = ["PRReviewAgent", "PRReviewInput", "PRReviewResult"]
