"""Pipeline Orchestrator — YAML-driven multi-agent coordination.

Reads `.agent-pipeline.yml`, selects the matching pipeline for a given event,
and executes agent steps (parallel or sequential). All output is routed through
FindingAggregator for a single unified comment.

No LLM required — deterministic orchestration logic.

Usage:
    from agent_sdlc.agents.pipeline_orchestrator import (
        PipelineOrchestrator,
        PipelineConfig,
        PipelineEvent,
        PipelineResult,
    )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from agent_sdlc.agents.finding_aggregator import (
    AgentFindings,
    AggregatorInput,
    AggregatorResult,
    FindingAggregator,
)
from agent_sdlc.core.findings import Finding, FindingSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config models (parsed from YAML)
# ---------------------------------------------------------------------------


class AgentStepConfig(BaseModel):
    """Configuration for a single agent within a pipeline step."""

    agent: str
    mode: Optional[str] = None
    consumes_upstream: bool = False
    trigger_on: Optional[str] = None
    on_failure: str = "continue"


class StepConfig(BaseModel):
    """A pipeline step: parallel, sequential, or always."""

    step_type: str = Field(description="One of: parallel, sequential, always")
    agents: List[AgentStepConfig] = Field(default_factory=list)


class TriggerConfig(BaseModel):
    event: str
    actions: List[str] = Field(default_factory=list)
    paths: List[str] = Field(default_factory=list)


class PipelineDef(BaseModel):
    """A named pipeline definition from .agent-pipeline.yml."""

    name: str
    triggers: List[TriggerConfig] = Field(default_factory=list)
    steps: List[StepConfig] = Field(default_factory=list)


class PipelineConfig(BaseModel):
    """Top-level config parsed from .agent-pipeline.yml."""

    pipelines: Dict[str, PipelineDef] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Runtime models
# ---------------------------------------------------------------------------


class PipelineEvent(BaseModel):
    """Describes the GitHub event that triggered the pipeline."""

    event: str = Field(description="e.g. 'pull_request', 'issues'")
    action: str = Field(default="", description="e.g. 'opened', 'synchronize'")
    changed_paths: List[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """Result of a full pipeline run."""

    pipeline_name: str
    aggregated: AggregatorResult
    steps_executed: int = 0
    aborted: bool = False
    abort_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent runner protocol
# ---------------------------------------------------------------------------

# AgentRunner: callable that takes (agent_name, mode, upstream_findings)
# and returns (findings, exit_code).
AgentRunner = Callable[
    [str, Optional[str], List[Finding]], tuple  # (List[Finding], int)
]


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def _parse_step(raw: Dict[str, Any]) -> StepConfig:
    """Parse a single step dict from the YAML steps list."""
    for step_type in ("parallel", "sequential", "always"):
        if step_type in raw:
            agents_raw = raw[step_type]
            agents = []
            for a in agents_raw:
                agents.append(AgentStepConfig(**a))
            return StepConfig(step_type=step_type, agents=agents)
    raise ValueError(f"Unknown step type in pipeline config: {raw}")


def load_pipeline_config(path: Path) -> PipelineConfig:
    """Load and parse .agent-pipeline.yml."""
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    pipelines: Dict[str, PipelineDef] = {}
    for name, pdef in raw.get("pipelines", {}).items():
        triggers = [TriggerConfig(**t) for t in pdef.get("triggers", [])]
        steps = [_parse_step(s) for s in pdef.get("steps", [])]
        pipelines[name] = PipelineDef(name=name, triggers=triggers, steps=steps)

    return PipelineConfig(pipelines=pipelines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class PipelineOrchestrator:
    """Executes a pipeline by running agent steps and aggregating findings.

    The orchestrator does not import or instantiate agents directly. Instead,
    it delegates to an ``AgentRunner`` callable provided at construction time.
    This keeps the orchestrator testable with DummyLLMProvider stubs and
    avoids circular imports.
    """

    def __init__(
        self,
        config: PipelineConfig,
        agent_runner: AgentRunner,
    ) -> None:
        self.config = config
        self.agent_runner = agent_runner
        self._aggregator = FindingAggregator()

    def match_pipeline(self, event: PipelineEvent) -> Optional[PipelineDef]:
        """Find the first pipeline whose triggers match the event."""
        for pdef in self.config.pipelines.values():
            for trigger in pdef.triggers:
                if trigger.event != event.event:
                    continue
                if trigger.actions and event.action not in trigger.actions:
                    continue
                if trigger.paths:
                    if not any(
                        self._path_matches(p, event.changed_paths)
                        for p in trigger.paths
                    ):
                        continue
                return pdef
        return None

    def run(
        self,
        event: PipelineEvent,
        pipeline_run_id: Optional[str] = None,
    ) -> Optional[PipelineResult]:
        """Execute the matching pipeline for the given event.

        Returns None if no pipeline matches.
        """
        pdef = self.match_pipeline(event)
        if pdef is None:
            return None

        all_agent_findings: List[AgentFindings] = []
        upstream_findings: List[Finding] = []
        steps_executed = 0

        for step in pdef.steps:
            if step.step_type == "always":
                # Always steps just run the aggregator — skip agent_runner
                steps_executed += 1
                continue

            step_findings, aborted, abort_reason = self._execute_step(
                step, upstream_findings
            )
            all_agent_findings.extend(step_findings)
            steps_executed += 1

            # Update upstream for next step
            for af in step_findings:
                upstream_findings.extend(af.findings)

            if aborted:
                aggregated = self._aggregate(
                    pipeline_run_id, all_agent_findings
                )
                return PipelineResult(
                    pipeline_name=pdef.name,
                    aggregated=aggregated,
                    steps_executed=steps_executed,
                    aborted=True,
                    abort_reason=abort_reason,
                )

        aggregated = self._aggregate(pipeline_run_id, all_agent_findings)
        return PipelineResult(
            pipeline_name=pdef.name,
            aggregated=aggregated,
            steps_executed=steps_executed,
        )

    def _execute_step(
        self,
        step: StepConfig,
        upstream_findings: List[Finding],
    ) -> tuple:  # (List[AgentFindings], bool aborted, Optional[str] reason)
        """Execute a parallel or sequential step."""
        results: List[AgentFindings] = []
        aborted = False
        abort_reason: Optional[str] = None

        for agent_cfg in step.agents:
            # Check trigger_on condition
            if agent_cfg.trigger_on == "blocker_present":
                has_blockers = any(
                    f.severity == FindingSeverity.BLOCKER for f in upstream_findings
                )
                if not has_blockers:
                    logger.info(
                        "Skipping %s: trigger_on=blocker_present but no blockers",
                        agent_cfg.agent,
                    )
                    continue

            # Determine what upstream to pass
            findings_input = upstream_findings if agent_cfg.consumes_upstream else []

            try:
                findings_list, exit_code = self.agent_runner(
                    agent_cfg.agent, agent_cfg.mode, findings_input
                )
            except Exception:
                logger.exception("Agent %s raised an exception", agent_cfg.agent)
                findings_list = []
                exit_code = 1

            af = AgentFindings(
                agent=agent_cfg.agent,
                step=step.step_type,
                findings=findings_list,
                exit_code=exit_code,
            )
            results.append(af)

            if exit_code != 0 and agent_cfg.on_failure == "abort":
                aborted = True
                abort_reason = f"Agent '{agent_cfg.agent}' failed with exit_code={exit_code} and on_failure=abort"
                break

        return results, aborted, abort_reason

    def _aggregate(
        self,
        pipeline_run_id: Optional[str],
        agent_findings: List[AgentFindings],
    ) -> AggregatorResult:
        inp = AggregatorInput(
            pipeline_run_id=pipeline_run_id,
            agent_findings=agent_findings,
        )
        return self._aggregator.run(inp)

    @staticmethod
    def _path_matches(pattern: str, changed_paths: List[str]) -> bool:
        """Simple glob-like path matching (supports trailing **)."""
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            return any(p.startswith(prefix) for p in changed_paths)
        return any(p == pattern for p in changed_paths)


__all__ = [
    "PipelineOrchestrator",
    "PipelineConfig",
    "PipelineEvent",
    "PipelineResult",
    "load_pipeline_config",
]
