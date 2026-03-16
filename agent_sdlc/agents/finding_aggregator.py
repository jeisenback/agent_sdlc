"""FindingAggregator — deterministic multi-agent finding merger.

Merges Finding lists from multiple agents, deduplicates overlapping findings,
resolves severity conflicts, and produces one unified result.

No LLM call required — all logic is deterministic.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity

_SEVERITY_RANK = {
    FindingSeverity.BLOCKER: 0,
    FindingSeverity.WARNING: 1,
    FindingSeverity.SUGGESTION: 2,
}


class AggregatorInput(BaseModel):
    finding_sets: List[Tuple[str, List[Finding]]]
    pr_number: Optional[int] = None


class AggregatorResult(BaseModel):
    findings: List[Finding]
    by_agent: Dict[str, List[Finding]]
    approved: bool

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION)


def _similarity(a: str, b: str) -> float:
    """Return a rough character-level similarity ratio between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    # Count matching bigrams (fast approximation, no extra deps)
    def bigrams(s: str) -> List[str]:
        return [s[i : i + 2] for i in range(len(s) - 1)]

    bg_a = bigrams(a.lower())
    bg_b = bigrams(b.lower())
    if not bg_a or not bg_b:
        return 1.0 if a.lower() == b.lower() else 0.0
    intersection = sum(1 for bg in bg_a if bg in bg_b)
    return (2 * intersection) / (len(bg_a) + len(bg_b))


def _is_duplicate(f1: Finding, f2: Finding, similarity_threshold: float = 0.8) -> bool:
    """Return True when f2 should be considered a duplicate of f1."""
    # Exact match on rule + location
    if f1.rule == f2.rule and f1.location == f2.location:
        return True
    # Near-duplicate message (regardless of rule)
    if _similarity(f1.message, f2.message) >= similarity_threshold:
        return True
    return False


class FindingAggregator:
    """Deterministic finding merger and deduplicator.

    Merges findings from multiple agents, resolves severity conflicts (same
    rule + location keeps highest severity), deduplicates near-duplicate
    messages (≥80% similarity), and sorts BLOCKER → WARNING → SUGGESTION.

    No LLM call — fully deterministic and testable offline.
    """

    def run(self, inp: AggregatorInput) -> AggregatorResult:
        by_agent: Dict[str, List[Finding]] = {}
        # Flatten all findings, tracking agent origin in a parallel list
        all_findings: List[Finding] = []
        all_agents: List[str] = []

        for agent_name, findings in inp.finding_sets:
            by_agent[agent_name] = list(findings)
            for f in findings:
                all_findings.append(f)
                all_agents.append(agent_name)

        # Deduplicate: iterate and keep a representative set
        kept: List[Finding] = []
        for i, candidate in enumerate(all_findings):
            duplicate = False
            for j, existing in enumerate(kept):
                if _is_duplicate(existing, candidate):
                    # Resolve severity conflict: keep highest severity
                    if (
                        _SEVERITY_RANK[candidate.severity]
                        < _SEVERITY_RANK[existing.severity]
                    ):
                        kept[j] = candidate
                    duplicate = True
                    break
            if not duplicate:
                kept.append(candidate)

        # Sort: BLOCKER → WARNING → SUGGESTION, then by rule for stability
        kept.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.rule, f.location))

        approved = not any(f.severity == FindingSeverity.BLOCKER for f in kept)
        return AggregatorResult(findings=kept, by_agent=by_agent, approved=approved)

    def to_markdown(
        self, result: AggregatorResult, pr_number: Optional[int] = None
    ) -> str:
        """Render a unified PR comment with agent attribution per finding."""
        pr_label = f"PR #{pr_number}" if pr_number else "Review"
        status = (
            "**Status: No blockers — eligible for merge (human approval required)**"
            if result.approved
            else "**Status: BLOCKED — blockers must be resolved before merge**"
        )
        lines = [f"## Unified Review — {pr_label}\n\n{status}\n"]

        # Build attribution map: finding index → agent name
        attribution: Dict[int, str] = {}
        for agent_name, agent_findings in result.by_agent.items():
            for af in agent_findings:
                for i, f in enumerate(result.findings):
                    if (
                        f.rule == af.rule
                        and f.location == af.location
                        and i not in attribution
                    ):
                        attribution[i] = agent_name

        if result.findings:
            lines.append("| Severity | Agent | Location | Rule | Message |")
            lines.append("|----------|-------|----------|------|---------|")
            for i, f in enumerate(result.findings):
                agent = attribution.get(i, "—")
                msg = f.message.replace("|", "\\|")
                lines.append(
                    f"| {f.severity.value} | {agent} | `{f.location}` | `{f.rule}` | {msg} |"
                )
        else:
            lines.append("_No findings across all agents._")

        return "\n".join(lines)


__all__ = ["FindingAggregator", "AggregatorInput", "AggregatorResult"]
