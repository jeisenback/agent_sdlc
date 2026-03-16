"""FindingAggregator — merges Finding lists from multiple agents.

Deterministic (no LLM required). Deduplicates findings by (rule, location),
resolves severity conflicts by keeping the highest severity, and produces one
unified finding list suitable for a single PR/issue comment.

Usage:
    from agent_sdlc.agents.finding_aggregator import (
        FindingAggregator,
        AggregatorInput,
        AggregatorResult,
    )
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from agent_sdlc.core.findings import Finding, FindingSeverity


# Severity ordering: higher numeric value = more severe
_SEVERITY_RANK: Dict[FindingSeverity, int] = {
    FindingSeverity.SUGGESTION: 0,
    FindingSeverity.WARNING: 1,
    FindingSeverity.BLOCKER: 2,
}


class AgentFindings(BaseModel):
    """Findings produced by a single agent step."""

    agent: str = Field(description="Agent name, e.g. 'pr_review'.")
    step: Optional[str] = Field(
        default=None, description="Pipeline step label, e.g. 'parallel-0'."
    )
    findings: List[Finding] = Field(default_factory=list)
    exit_code: int = Field(default=0, description="0 = success, 1 = failure.")


class AggregatorInput(BaseModel):
    """Input to FindingAggregator: a collection of per-agent finding sets."""

    pipeline_run_id: Optional[str] = None
    agent_findings: List[AgentFindings] = Field(default_factory=list)


class AggregatorResult(BaseModel):
    """Unified output from FindingAggregator."""

    pipeline_run_id: Optional[str] = None
    findings: List[Finding] = Field(default_factory=list)
    agents_ran: List[str] = Field(default_factory=list)
    agents_failed: List[str] = Field(default_factory=list)

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


class FindingAggregator:
    """Merges findings from multiple agents into a single deduplicated list.

    Deduplication key: (rule, location). When two findings share the same key,
    the one with the higher severity wins. If severities are equal, the first
    occurrence is kept.

    No LLM required — fully deterministic.
    """

    def run(self, inp: AggregatorInput) -> AggregatorResult:
        agents_ran: List[str] = []
        agents_failed: List[str] = []
        seen: Dict[tuple, Finding] = {}  # (rule, location) -> Finding

        for af in inp.agent_findings:
            agents_ran.append(af.agent)
            if af.exit_code != 0:
                agents_failed.append(af.agent)

            for finding in af.findings:
                key = (finding.rule, finding.location)
                existing = seen.get(key)
                if existing is None:
                    seen[key] = finding
                elif _SEVERITY_RANK[finding.severity] > _SEVERITY_RANK[
                    existing.severity
                ]:
                    seen[key] = finding

        merged = list(seen.values())
        merged.sort(
            key=lambda f: (-_SEVERITY_RANK[f.severity], f.rule, f.location)
        )

        return AggregatorResult(
            pipeline_run_id=inp.pipeline_run_id,
            findings=merged,
            agents_ran=agents_ran,
            agents_failed=agents_failed,
        )


__all__ = ["FindingAggregator", "AggregatorInput", "AggregatorResult", "AgentFindings"]
