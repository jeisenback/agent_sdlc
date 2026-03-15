from __future__ import annotations

from typing import List

from pydantic import BaseModel

from agent_sdlc.core.findings import (Finding, FindingSeverity,
                                      parse_findings_from_json)
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
            f"You are a Definition of Ready (DoR) reviewer for software issues.\n"
            f"Check whether this issue is ready to enter a sprint.\n\n"
            f"Issue title: '{inp.title}'\n"
            f"Issue description:\n{inp.description}\n\n"
            f"Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            f'{{"location":"body|title|labels|ac","severity":"blocker|warning|suggestion",'
            f'"rule":"DoR:<rule-id>","message":"<what is wrong>","suggestion":"<how to fix>"}}\n'
            f'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            f"DoR rules to check:\n"
            f"  DoR:ac-count      — must have at least 2 acceptance criteria (BLOCKER if missing)\n"
            f"  DoR:ac-testable   — each AC must be verifiable/measurable (BLOCKER if vague)\n"
            f"  DoR:scope-clear   — scope must be unambiguous (BLOCKER if unclear)\n"
            f"  DoR:dependencies  — external dependencies must be named (WARNING if unstated)\n"
            f"  DoR:size          — issue should be completable in one sprint (WARNING if too large)\n"
            f"  DoR:title         — title must be specific, not generic (WARNING if vague)\n\n"
            f"Return [] if all DoR criteria are met."
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
