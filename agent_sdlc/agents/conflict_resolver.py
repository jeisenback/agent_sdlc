"""agent_sdlc/agents/conflict_resolver.py

AgentConflictResolver — adjudicates contradictory findings from multiple
agents and produces a single canonical verdict.

Structural conflicts (same rule, different severity) are resolved
deterministically (higher severity wins). Semantic contradictions
(different rules, contradictory meaning) use an LLM. Ambiguous conflicts
are escalated for human review.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {
    FindingSeverity.BLOCKER: 2,
    FindingSeverity.WARNING: 1,
    FindingSeverity.SUGGESTION: 0,
}

_CONFIDENCE_THRESHOLD = 0.7

_SEMANTIC_PROMPT = """\
Two agents reviewed the same artifact and produced seemingly contradictory findings.
Determine whether these findings genuinely contradict each other or are complementary.

Artifact (excerpt):
{artifact}

Finding A (from {agent_a}):
Rule: {rule_a}
Severity: {sev_a}
Message: {msg_a}

Finding B (from {agent_b}):
Rule: {rule_b}
Severity: {sev_b}
Message: {msg_b}

Respond with a JSON object ONLY:
{{
  "contradiction": true | false,
  "confidence": 0.0-1.0,
  "winner": "A" | "B" | "both" | "neither",
  "rationale": "<one sentence>"
}}

- contradiction: true if these are genuinely contradictory
- confidence: your confidence in this assessment (0.0-1.0)
- winner: which finding should be kept ("both" if complementary, "neither" if both invalid)
- rationale: brief explanation
"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConflictInput(BaseModel):
    finding_sets: List[Tuple[str, List[Finding]]]  # (agent_name, findings) pairs
    artifact: str


class ConflictResult(BaseModel):
    resolved_findings: List[Finding]
    conflicts: List[Dict[str, Any]]  # each resolved conflict with rationale
    escalated: List[Dict[str, Any]]  # conflicts flagged for human review


# ---------------------------------------------------------------------------
# Structural conflict detection (deterministic)
# ---------------------------------------------------------------------------


def _find_structural_conflicts(
    finding_sets: List[Tuple[str, List[Finding]]],
) -> Dict[str, List[Tuple[str, Finding]]]:
    """Return map of rule → [(agent_name, finding)] for rules with multiple severities."""
    by_rule: Dict[str, List[Tuple[str, Finding]]] = {}
    for agent_name, findings in finding_sets:
        for f in findings:
            key = f"{f.rule}::{f.location}"
            by_rule.setdefault(key, []).append((agent_name, f))

    # Keep only groups where there is more than one distinct severity
    conflicts = {}
    for key, group in by_rule.items():
        severities = {f.severity for _, f in group}
        if len(severities) > 1:
            conflicts[key] = group
    return conflicts


def _resolve_structural(
    key: str, group: List[Tuple[str, Finding]]
) -> Tuple[Finding, Dict[str, Any]]:
    """Take the highest severity finding; return it plus a conflict record."""
    best_agent, best_finding = max(group, key=lambda x: _SEVERITY_ORDER[x[1].severity])
    conflict_record = {
        "type": "structural",
        "rule": best_finding.rule,
        "location": best_finding.location,
        "agents": [a for a, _ in group],
        "original_severities": [f.severity.value for _, f in group],
        "resolution": best_finding.severity.value,
        "rationale": (
            f"Same rule at same location with different severities; "
            f"highest severity ({best_finding.severity.value}) from '{best_agent}' kept."
        ),
    }
    return best_finding, conflict_record


# ---------------------------------------------------------------------------
# Semantic conflict detection (LLM-driven)
# ---------------------------------------------------------------------------


def _parse_semantic_response(text: str) -> Optional[Dict]:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None


def _check_semantic_pair(
    agent_a: str,
    finding_a: Finding,
    agent_b: str,
    finding_b: Finding,
    artifact: str,
    provider: ProviderProtocol,
) -> Optional[Dict]:
    """Ask LLM whether two findings are semantically contradictory."""
    prompt = _SEMANTIC_PROMPT.format(
        artifact=artifact[:1000],
        agent_a=agent_a,
        rule_a=finding_a.rule,
        sev_a=finding_a.severity.value,
        msg_a=finding_a.message,
        agent_b=agent_b,
        rule_b=finding_b.rule,
        sev_b=finding_b.severity.value,
        msg_b=finding_b.message,
    )
    try:
        response = provider.complete(prompt)
        return _parse_semantic_response(response.content)
    except Exception as exc:
        logger.warning("Semantic conflict check failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# AgentConflictResolver
# ---------------------------------------------------------------------------


class AgentConflictResolver:
    """Adjudicates contradictory findings from multiple agents."""

    def __init__(self, provider: ProviderProtocol) -> None:
        self.provider = provider

    def run(self, inp: ConflictInput) -> ConflictResult:
        resolved: List[Finding] = []
        conflicts: List[Dict[str, Any]] = []
        escalated: List[Dict[str, Any]] = []

        # Collect all findings with agent attribution
        all_findings_with_agent: List[Tuple[str, Finding]] = []
        for agent_name, findings in inp.finding_sets:
            for f in findings:
                all_findings_with_agent.append((agent_name, f))

        # Step 1: Resolve structural conflicts
        structural = _find_structural_conflicts(inp.finding_sets)

        # Track which findings were handled structurally
        handled_keys: set = set()
        for key, group in structural.items():
            winner, record = _resolve_structural(key, group)
            resolved.append(winner)
            conflicts.append(record)
            handled_keys.add(key)

        # Step 2: Collect non-conflicting findings (not handled above)
        # De-duplicate: same rule+location → only one copy
        seen_keys: set = set()
        remaining: List[Tuple[str, Finding]] = []
        for agent_name, f in all_findings_with_agent:
            key = f"{f.rule}::{f.location}"
            if key in handled_keys:
                continue
            if key not in seen_keys:
                seen_keys.add(key)
                remaining.append((agent_name, f))

        # Step 3: Semantic conflict detection among remaining findings
        # Check pairs of BLOCKER/WARNING findings from different agents
        checked_pairs: set = set()
        semantic_handled: set = set()

        for i, (agent_a, f_a) in enumerate(remaining):
            if f_a.severity == FindingSeverity.SUGGESTION:
                continue
            for j, (agent_b, f_b) in enumerate(remaining):
                if i >= j or agent_a == agent_b:
                    continue
                if f_b.severity == FindingSeverity.SUGGESTION:
                    continue
                pair_key = tuple(sorted([i, j]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                verdict = _check_semantic_pair(
                    agent_a, f_a, agent_b, f_b, inp.artifact, self.provider
                )
                if verdict is None or not verdict.get("contradiction", False):
                    continue

                confidence = float(verdict.get("confidence", 0.0))
                winner = verdict.get("winner", "both")
                rationale = verdict.get("rationale", "")

                if confidence < _CONFIDENCE_THRESHOLD:
                    escalated.append(
                        {
                            "type": "semantic",
                            "agents": [agent_a, agent_b],
                            "findings": [f_a.dict(), f_b.dict()],
                            "rationale": rationale,
                            "confidence": confidence,
                            "label": "needs-human-review",
                        }
                    )
                    semantic_handled.update([i, j])
                else:
                    conflict_record = {
                        "type": "semantic",
                        "agents": [agent_a, agent_b],
                        "winner": winner,
                        "rationale": rationale,
                        "confidence": confidence,
                    }
                    conflicts.append(conflict_record)
                    if winner in ("A", "both"):
                        if i not in semantic_handled:
                            resolved.append(f_a)
                            semantic_handled.add(i)
                    if winner in ("B", "both"):
                        if j not in semantic_handled:
                            resolved.append(f_b)
                            semantic_handled.add(j)
                    if winner == "neither":
                        semantic_handled.update([i, j])

        # Step 4: Add all unhandled remaining findings
        for idx, (_, f) in enumerate(remaining):
            if idx not in semantic_handled:
                resolved.append(f)

        return ConflictResult(
            resolved_findings=resolved,
            conflicts=conflicts,
            escalated=escalated,
        )


__all__ = ["AgentConflictResolver", "ConflictInput", "ConflictResult"]
