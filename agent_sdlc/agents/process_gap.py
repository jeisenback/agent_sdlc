from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class ProcessGapInput(BaseModel):
    title: str
    description: str
    mode: Literal["issue"] = "issue"


class ProcessGapResult(BaseModel):
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


class ProcessGapAgent:
    """Business-side process gap agent for issues (mode=issue).

    Checks whether an issue has sufficient business context — the "why",
    measurable outcomes, target user, and rollback plan. Complements
    IssueRefinementAgent (which checks formatting/DoR) by asking whether
    the issue *should* be built and whether the business context is complete.

    Rules namespace: biz:
    Returns a ProcessGapResult with a Finding list; approved=False if any
    BLOCKER findings are present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: ProcessGapInput) -> ProcessGapResult:
        prompt = (
            "You are a business process reviewer for software issues.\n"
            "Check whether this issue has sufficient business context to proceed.\n\n"
            f"Issue title: '{inp.title}'\n"
            f"Issue description:\n{inp.description}\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            '{"location":"title|description|ac|labels","severity":"blocker|warning|suggestion",'
            '"rule":"biz:<rule-id>","message":"<what is missing>","suggestion":"<how to fix>"}\n'
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "Business process rules to check (namespace biz:):\n"
            "  biz:no-why              — No stated business value: the issue explains what to build but\n"
            "                            not why it matters or what problem it solves (BLOCKER)\n"
            "  biz:no-success-metric   — No measurable outcome: no KPI, metric, or verifiable result\n"
            "                            defined so the team can tell when this is done (BLOCKER)\n"
            "  biz:no-target-user      — No identified user: no persona, segment, or role that benefits\n"
            "                            from this change is mentioned (BLOCKER)\n"
            "  biz:scope-creep-risk    — The issue appears to address multiple unrelated concerns or\n"
            "                            bundle features that should be separate issues (WARNING)\n"
            "  biz:no-stakeholder      — No product owner or decision-maker is identified as responsible\n"
            "                            for this work (WARNING)\n"
            "  biz:no-rollback-plan    — No mention of what happens if the change needs to be reverted\n"
            "                            or rolled back in production (SUGGESTION)\n"
            "  biz:no-uat-gate         — No acceptance step before production is defined: no mention\n"
            "                            of UAT, canary, or staged rollout (SUGGESTION)\n\n"
            "Return [] if all business process criteria are met."
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return ProcessGapResult(findings=findings)


__all__ = ["ProcessGapAgent", "ProcessGapInput", "ProcessGapResult"]
