from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class UXInput(BaseModel):
    flow_description: str
    user_goal: str
    user_type: Optional[str] = None
    flow_context: Optional[str] = None


class UXResult(BaseModel):
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


class UXAgent:
    """User flow friction and usability review agent.

    Reviews prose user flow descriptions for interaction friction, missing
    error states, dead ends, and CTA clarity. Operates on flow descriptions,
    not source code. Complementary to UIDesignAgent (visual).

    Rules namespace: UX:
    Returns a UXResult; approved=False if any BLOCKER findings present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: UXInput) -> UXResult:
        user_type_ctx = f"\nUser type: {inp.user_type}" if inp.user_type else ""
        flow_context_ctx = (
            f"\nFlow context: {inp.flow_context}" if inp.flow_context else ""
        )
        mobile_note = (
            "\n  UX:mobile-friction     — Hover-dependent or mouse-only interactions that\n"
            "                            are problematic on touch/mobile devices (SUGGESTION)\n"
            if inp.user_type and "mobile" in inp.user_type.lower()
            else ""
        )
        prompt = (
            "You are a UX reviewer analysing a user flow description for friction,\n"
            "usability gaps, and missing interaction states.\n\n"
            f"User goal: {inp.user_goal}"
            f"{user_type_ctx}{flow_context_ctx}\n\n"
            f"Flow description:\n{inp.flow_description}\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            '{"location":"<step name or flow section>","severity":"blocker|warning|suggestion",'
            '"rule":"UX:<rule-id>","message":"<what is wrong>","suggestion":"<how to fix>"}\n'
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "UX rules to check (namespace UX:):\n"
            "  UX:no-error-state       — The flow has no description of what happens when an\n"
            "                            action fails (network error, validation failure, timeout).\n"
            "                            Users must always know what went wrong and what to do next.\n"
            "                            (BLOCKER)\n"
            "  UX:no-success-feedback  — The flow ends without any confirmation to the user that\n"
            "                            their goal was achieved (no success message, redirect, or\n"
            "                            visual indicator). (BLOCKER)\n"
            "  UX:dead-end             — A path in the flow reaches a terminal state (step with no\n"
            "                            described next action or recovery route). (BLOCKER)\n"
            "  UX:step-count-high      — The flow requires more than 5 distinct user actions before\n"
            "                            the goal is completed. (WARNING)\n"
            "  UX:ambiguous-cta        — A call-to-action label is generic ('Submit', 'Click here',\n"
            "                            'OK') with no outcome implied by the label. (WARNING)\n"
            "  UX:undo-missing         — A destructive action (delete, overwrite, send) has no undo\n"
            "                            option or confirmation step. (WARNING)\n"
            "  UX:context-lost         — The user must navigate away from the current view and\n"
            "                            re-orient to complete the flow (breaks mental model). (WARNING)\n"
            "  UX:loading-unaddressed  — A slow or async operation has no described loading state,\n"
            "                            progress indicator, or placeholder. (SUGGESTION)\n"
            f"{mobile_note}"
            "\nReturn [] if the flow passes all UX checks."
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return UXResult(findings=findings)


__all__ = ["UXAgent", "UXInput", "UXResult"]
