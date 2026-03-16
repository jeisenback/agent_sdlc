"""agent_sdlc/agents/routing_orchestrator.py

RoutingOrchestrator — LLM-driven dynamic agent selection.

Given event context (trigger, changed files, labels), selects which agents
to invoke and in what order — adapts to content in ways static YAML cannot.

When ANTHROPIC_API_KEY is not set or the LLM is unavailable, falls back to
the static YAML pipeline config (same behaviour as Pipeline Orchestrator).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel

from agent_sdlc.core.providers import ProviderProtocol

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = ".agent-pipeline.yml"

_ROUTING_PROMPT = """\
You are a CI orchestration expert. Given the event context below, decide
which review agents should run and in what order.

Available agents: {available_agents}

Event context:
- Trigger: {trigger}
- Changed files: {changed_files}
- Labels: {labels}
- Summary: {context}

Respond with a JSON object ONLY (no markdown):
{{
  "steps": [
    {{"parallel": ["agent_name1", "agent_name2"]}},
    {{"sequential": ["agent_name3"]}}
  ],
  "rationale": "<one or two sentences explaining your selection>"
}}

Rules:
- Include only agents relevant to the changed content.
- For docs-only changes, skip arch_review and prompt_review.
- Always include finding_aggregator as the final step.
- Limit to 3-5 agents unless the change is very broad.
"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RoutingStep(BaseModel):
    """A single step in the routing plan, compatible with run_pipeline.py."""

    agents: List[str]
    parallel: bool = True


class RoutingPlan(BaseModel):
    steps: List[Dict[str, Any]]  # pipeline-compatible step dicts
    rationale: str
    fallback_used: bool


class RoutingInput(BaseModel):
    trigger: str
    context: str
    changed_files: List[str]
    labels: List[str]
    available_agents: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_yaml_pipeline(
    config_path: str, trigger: str
) -> Optional[List[Dict[str, Any]]]:
    """Load static YAML pipeline steps for the trigger."""
    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh)
        return cfg.get("pipelines", {}).get(trigger, {}).get("steps")
    except (OSError, KeyError):
        return None


def _parse_routing_response(text: str, available: List[str]) -> Optional[Dict]:
    """Parse LLM routing JSON response."""
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None

    # Validate that returned agents are in available list
    steps = data.get("steps", [])
    validated_steps = []
    for step in steps:
        if "parallel" in step:
            agents = [a for a in step["parallel"] if a in available]
            if agents:
                validated_steps.append(
                    {
                        "parallel": [
                            {"agent": a, "on_failure": "continue"} for a in agents
                        ]
                    }
                )
        elif "sequential" in step:
            agents = [a for a in step["sequential"] if a in available]
            if agents:
                validated_steps.append(
                    {
                        "sequential": [
                            {"agent": a, "on_failure": "continue"} for a in agents
                        ]
                    }
                )

    data["steps"] = validated_steps
    return data


def _write_routing_log(plan: RoutingPlan, path: str = "routing_log.json") -> None:
    """Write routing decisions to a JSON artifact for auditability."""
    try:
        with open(path, "w") as fh:
            json.dump(
                {
                    "steps": plan.steps,
                    "rationale": plan.rationale,
                    "fallback_used": plan.fallback_used,
                },
                fh,
                indent=2,
            )
        logger.info("Routing log written to %s", path)
    except OSError as exc:
        logger.warning("Could not write routing log: %s", exc)


# ---------------------------------------------------------------------------
# RoutingOrchestrator
# ---------------------------------------------------------------------------


class RoutingOrchestrator:
    """LLM-driven dynamic agent selection with YAML fallback."""

    def __init__(
        self,
        provider: ProviderProtocol,
        config_path: str = _DEFAULT_CONFIG,
        log_path: str = "routing_log.json",
    ) -> None:
        self.provider = provider
        self.config_path = config_path
        self.log_path = log_path

    def run(self, inp: RoutingInput) -> RoutingPlan:
        plan = self._route_with_llm(inp)
        if plan is None:
            plan = self._fallback_to_yaml(inp)

        _write_routing_log(plan, self.log_path)
        return plan

    def _route_with_llm(self, inp: RoutingInput) -> Optional[RoutingPlan]:
        """Ask the LLM to select agents. Returns None on failure."""
        prompt = _ROUTING_PROMPT.format(
            available_agents=", ".join(inp.available_agents),
            trigger=inp.trigger,
            changed_files=", ".join(inp.changed_files[:20]) or "(none)",
            labels=", ".join(inp.labels) or "(none)",
            context=inp.context[:500],
        )
        try:
            response = self.provider.complete(prompt)
            parsed = _parse_routing_response(response.content, inp.available_agents)
        except Exception as exc:
            logger.warning("RoutingOrchestrator: LLM call failed — %s", exc)
            return None

        if parsed is None:
            logger.warning(
                "RoutingOrchestrator: could not parse LLM response; using fallback"
            )
            return None

        return RoutingPlan(
            steps=parsed.get("steps", []),
            rationale=parsed.get("rationale", "LLM-selected"),
            fallback_used=False,
        )

    def _fallback_to_yaml(self, inp: RoutingInput) -> RoutingPlan:
        """Fall back to static YAML pipeline config."""
        logger.info(
            "RoutingOrchestrator: falling back to YAML config for trigger '%s'",
            inp.trigger,
        )
        steps = _load_yaml_pipeline(self.config_path, inp.trigger) or []
        return RoutingPlan(
            steps=steps,
            rationale="Fallback to static YAML pipeline config.",
            fallback_used=True,
        )


__all__ = [
    "RoutingOrchestrator",
    "RoutingInput",
    "RoutingPlan",
    "RoutingStep",
]
