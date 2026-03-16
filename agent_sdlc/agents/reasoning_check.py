"""agent_sdlc/agents/reasoning_check.py

ReasoningCheckAgent — verifies that upstream BLOCKER findings are
logically sound before they block CI. Prevents hallucinated or
miscalibrated findings from failing work.

Sprint 2: scaffold (class, models, unit tests with DummyLLMProvider).
Sprint 3: activate with real LLM for production verification.
"""

from __future__ import annotations

import json
import logging
from typing import List, Literal, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol

logger = logging.getLogger(__name__)

ArtifactType = Literal["diff", "issue", "agent_source", "flow"]
TriggerReason = Literal["blocker", "planning", "error", "miscommunication"]

_VERIFY_PROMPT = """\
You are a senior engineer reviewing whether the following BLOCKER finding is
logically supported by the artifact.

Artifact type: {artifact_type}
Upstream agent: {upstream_agent}
Trigger: {trigger_reason}

--- ARTIFACT ---
{artifact}

--- FINDING ---
Rule: {rule}
Message: {message}
Location: {location}

Respond with a JSON object:
{{
  "action": "keep" | "downgrade" | "remove",
  "reason": "<one-sentence justification>",
  "rule": "Reason:<specific-rule>"
}}

- "keep": finding is clearly supported by the artifact
- "downgrade": finding is real but severity overstated (change to WARNING)
- "remove": finding is not supported by evidence in the artifact
"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ReasoningCheckInput(BaseModel):
    artifact: str
    artifact_type: ArtifactType
    upstream_agent: str
    findings: List[Finding]
    trigger_reason: TriggerReason


class ReasoningCheckResult(BaseModel):
    verified_findings: List[Finding]  # findings that passed verification
    downgraded: List[Finding]  # BLOCKERs downgraded to WARNING
    removed: List[Finding]  # findings removed as unsupported
    approved: bool  # True when zero BLOCKERs remain after verification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_verification(text: str) -> Optional[dict]:
    """Parse a single verification JSON response."""
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None


def _detect_contradictions(findings: List[Finding]) -> List[Finding]:
    """Return BLOCKER findings that contradict another from the same source."""
    contradictions = []
    blockers = [f for f in findings if f.severity == FindingSeverity.BLOCKER]
    for i, f1 in enumerate(blockers):
        for f2 in blockers[i + 1 :]:
            # Simple heuristic: same location, different rules — potential conflict
            if f1.location == f2.location and f1.rule != f2.rule:
                logger.info(
                    "Potential contradiction: %s vs %s at %s",
                    f1.rule,
                    f2.rule,
                    f1.location,
                )
                if f1 not in contradictions:
                    contradictions.append(f1)
                if f2 not in contradictions:
                    contradictions.append(f2)
    return contradictions


# ---------------------------------------------------------------------------
# ReasoningCheckAgent
# ---------------------------------------------------------------------------


class ReasoningCheckAgent:
    """Verifies BLOCKER findings are evidence-based before they block CI."""

    def __init__(self, provider: ProviderProtocol) -> None:
        self.provider = provider

    def run(self, inp: ReasoningCheckInput) -> ReasoningCheckResult:
        verified: List[Finding] = []
        downgraded: List[Finding] = []
        removed: List[Finding] = []

        # Only verify BLOCKER findings; pass others through unchanged
        non_blockers = [
            f for f in inp.findings if f.severity != FindingSeverity.BLOCKER
        ]
        blockers = [f for f in inp.findings if f.severity == FindingSeverity.BLOCKER]

        # Log contradiction detection for miscommunication trigger
        if inp.trigger_reason == "miscommunication":
            contradictions = _detect_contradictions(blockers)
            if contradictions:
                logger.warning(
                    "ReasoningCheckAgent: %d contradicting BLOCKER findings detected",
                    len(contradictions),
                )

        for finding in blockers:
            prompt = _VERIFY_PROMPT.format(
                artifact_type=inp.artifact_type,
                upstream_agent=inp.upstream_agent,
                trigger_reason=inp.trigger_reason,
                artifact=inp.artifact[:2000],  # truncate for token budget
                rule=finding.rule,
                message=finding.message,
                location=finding.location,
            )
            try:
                response = self.provider.complete(prompt)
                parsed = _parse_verification(response.content)
            except Exception as exc:
                logger.warning(
                    "ReasoningCheckAgent: provider error for finding %s — %s; keeping",
                    finding.rule,
                    exc,
                )
                parsed = None

            if parsed is None:
                # Fallback: keep the finding unchanged
                verified.append(finding)
                continue

            action = parsed.get("action", "keep")
            reason_rule = parsed.get("rule", "Reason:unsupported-blocker")

            if action == "remove":
                removed_finding = finding.copy(
                    update={
                        "rule": reason_rule,
                        "message": f"{finding.message} [removed: {parsed.get('reason', '')}]",
                    }
                )
                removed.append(removed_finding)
            elif action == "downgrade":
                downgraded_finding = finding.copy(
                    update={
                        "severity": FindingSeverity.WARNING,
                        "message": f"{finding.message} [downgraded: {parsed.get('reason', '')}]",
                    }
                )
                downgraded.append(downgraded_finding)
            else:
                # "keep" or unknown → pass through
                verified.append(finding)

        # All non-blockers pass through
        verified.extend(non_blockers)

        all_remaining = verified + downgraded
        approved = all(f.severity != FindingSeverity.BLOCKER for f in all_remaining)

        return ReasoningCheckResult(
            verified_findings=verified,
            downgraded=downgraded,
            removed=removed,
            approved=approved,
        )


__all__ = [
    "ReasoningCheckAgent",
    "ReasoningCheckInput",
    "ReasoningCheckResult",
]
