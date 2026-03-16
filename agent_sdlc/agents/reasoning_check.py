"""ReasoningCheckAgent — verifies BLOCKER findings before they block work.

Scaffold (Sprint 2): deterministic sanity checks on upstream findings.
Sprint 3 activation: with a real LLM provider, performs deeper reasoning
verification (logic soundness, severity justification, missing findings).

Triggers when:
  - Upstream agent produces >= 1 BLOCKER finding
  - Issue labelled ``planning``
  - Detected agent error/miscommunication

Takes the original artifact + upstream findings; verifies each finding's
logic, severity, and completeness. May downgrade or remove hallucinated
BLOCKERs. A BLOCKER from ReasoningCheck itself blocks merge.

Rules namespace: ``Reason:``

Usage:
    from agent_sdlc.agents.reasoning_check import (
        ReasoningCheckAgent,
        ReasoningCheckInput,
        ReasoningCheckResult,
    )
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class ReasoningCheckInput(BaseModel):
    """Input for reasoning verification."""

    artifact: str = Field(
        description="The original artifact (diff, issue body, source) that was reviewed."
    )
    upstream_findings: List[Finding] = Field(
        default_factory=list,
        description="Findings from upstream agents to verify.",
    )
    trigger_reason: str = Field(
        default="blocker_present",
        description="Why this check was triggered.",
    )


class ReasoningCheckResult(BaseModel):
    """Result of reasoning verification."""

    findings: List[Finding] = Field(default_factory=list)
    verified_findings: List[Finding] = Field(
        default_factory=list,
        description="Upstream findings that passed verification.",
    )
    downgraded_findings: List[Finding] = Field(
        default_factory=list,
        description="Upstream findings whose severity was reduced.",
    )
    removed_findings: List[Finding] = Field(
        default_factory=list,
        description="Upstream findings removed as unsound.",
    )

    @property
    def approved(self) -> bool:
        return not any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION
        )


class ReasoningCheckAgent:
    """Verifies upstream BLOCKER findings for logical soundness.

    Without a provider (Sprint 2 scaffold): runs deterministic sanity checks.
    With a provider (Sprint 3): uses LLM to reason about finding validity.
    """

    def __init__(self, provider: Optional[ProviderProtocol] = None) -> None:
        self.provider = provider
        self._llm = LLMWrapper(provider) if provider else None

    def run(self, inp: ReasoningCheckInput) -> ReasoningCheckResult:
        if self._llm is not None:
            return self._run_with_llm(inp)
        return self._run_deterministic(inp)

    # ------------------------------------------------------------------
    # Sprint 2: deterministic scaffold
    # ------------------------------------------------------------------

    def _run_deterministic(self, inp: ReasoningCheckInput) -> ReasoningCheckResult:
        """Deterministic sanity checks on upstream findings."""
        own_findings: List[Finding] = []
        verified: List[Finding] = []
        downgraded: List[Finding] = []
        removed: List[Finding] = []

        for finding in inp.upstream_findings:
            issues = self._check_finding_quality(finding)
            if issues:
                # Finding has quality issues — downgrade if BLOCKER
                if finding.severity == FindingSeverity.BLOCKER:
                    downgraded_copy = finding.copy(
                        update={"severity": FindingSeverity.WARNING}
                    ) if hasattr(finding, "copy") else Finding(
                        location=finding.location,
                        line_number=finding.line_number,
                        severity=FindingSeverity.WARNING,
                        rule=finding.rule,
                        message=finding.message,
                        suggestion=finding.suggestion,
                    )
                    downgraded.append(downgraded_copy)
                    own_findings.append(
                        Finding(
                            location=finding.location,
                            severity=FindingSeverity.WARNING,
                            rule="Reason:quality-issue",
                            message=f"Upstream finding '{finding.rule}' has quality issues: {'; '.join(issues)}. Downgraded from BLOCKER.",
                            suggestion="Review the original finding and provide more detail.",
                        )
                    )
                else:
                    verified.append(finding)
            else:
                verified.append(finding)

        return ReasoningCheckResult(
            findings=own_findings,
            verified_findings=verified,
            downgraded_findings=downgraded,
            removed_findings=removed,
        )

    def _check_finding_quality(self, finding: Finding) -> List[str]:
        """Return list of quality issues with a finding. Empty = passes."""
        issues: List[str] = []

        # Rule: empty or generic message
        if not finding.message or len(finding.message.strip()) < 10:
            issues.append("message too short or empty")

        # Rule: BLOCKER with no suggestion
        if finding.severity == FindingSeverity.BLOCKER and not finding.suggestion:
            issues.append("BLOCKER finding has no suggestion for resolution")

        # Rule: missing rule ID
        if not finding.rule or finding.rule == "general":
            issues.append("finding has no specific rule ID")

        return issues

    # ------------------------------------------------------------------
    # Sprint 3: LLM-based verification
    # ------------------------------------------------------------------

    def _run_with_llm(self, inp: ReasoningCheckInput) -> ReasoningCheckResult:
        """LLM-based reasoning verification (Sprint 3)."""
        assert self._llm is not None

        findings_text = "\n".join(
            f"- [{f.severity.value}] {f.rule}: {f.message} (at {f.location})"
            for f in inp.upstream_findings
        )

        prompt = (
            "You are a reasoning verification agent. Your job is to check whether "
            "the following findings from an upstream review agent are logically sound, "
            "have justified severity, and whether any obvious findings are missing.\n\n"
            f"ARTIFACT:\n{inp.artifact}\n\n"
            f"UPSTREAM FINDINGS:\n{findings_text}\n\n"
            "For each finding, assess:\n"
            "1. Is the logic sound? Does the evidence support the conclusion?\n"
            "2. Is the severity justified? Should it be BLOCKER/WARNING/SUGGESTION?\n"
            "3. Are there obvious findings missing from the review?\n\n"
            "Return ONLY a raw JSON array of your own findings. Each element:\n"
            '{"location":"<ref>","severity":"blocker|warning|suggestion",'
            '"rule":"Reason:<rule-id>","message":"<assessment>",'
            '"suggestion":"<recommendation>"}\n\n'
            "Rules:\n"
            "  Reason:unsound — finding logic does not hold (BLOCKER if original was BLOCKER)\n"
            "  Reason:severity-mismatch — severity not justified by evidence (WARNING)\n"
            "  Reason:missing-finding — obvious issue not caught by upstream (WARNING)\n"
            "  Reason:hallucinated — finding references non-existent code/issue (BLOCKER)\n\n"
            "Return [] if all upstream findings are sound."
        )
        text = self._llm.ask_text(prompt)
        own_findings = parse_findings_from_json(text)

        # For Sprint 3, we still verify upstream deterministically
        # and merge with LLM findings
        det_result = self._run_deterministic(inp)
        all_findings = det_result.findings + own_findings

        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        all_findings.sort(key=lambda f: _order[f.severity])

        return ReasoningCheckResult(
            findings=all_findings,
            verified_findings=det_result.verified_findings,
            downgraded_findings=det_result.downgraded_findings,
            removed_findings=det_result.removed_findings,
        )


__all__ = ["ReasoningCheckAgent", "ReasoningCheckInput", "ReasoningCheckResult"]
