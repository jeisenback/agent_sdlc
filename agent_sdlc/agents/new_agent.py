"""agent_sdlc/agents/new_agent.py

NewAgentAgent — scaffolds a new, pattern-compliant agent from a description
and rule definitions. After generation, validates the scaffold with
AgentReviewAgent before returning.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding
from agent_sdlc.core.providers import ProviderProtocol

logger = logging.getLogger(__name__)

_SCAFFOLD_PROMPT = """\
You are an expert Python engineer who writes clean, pattern-compliant agents
for the agent_sdlc framework.

Generate a complete agent scaffold from the spec below. Return ONLY a JSON
object with four string fields (no markdown, no explanation):
{{
  "agent_source": "...",
  "runner_source": "...",
  "test_source": "...",
  "pipeline_entry": "..."
}}

=== AGENT SPEC ===
Name (snake_case): {name}
Description: {description}
Trigger: {trigger}

Rules:
{rules_block}

Input fields:
{fields_block}

=== REQUIREMENTS ===
agent_source MUST:
- import ProviderProtocol from agent_sdlc.core.providers
- import Finding, FindingSeverity from agent_sdlc.core.findings
- define {name_pascal}Input(BaseModel) with the specified input fields
- define {name_pascal}Result(BaseModel) with findings: List[Finding] and approved: bool
- define class {name_pascal}Agent with __init__(self, provider: ProviderProtocol)
- define run(self, inp: {name_pascal}Input) -> {name_pascal}Result
- export __all__ = ["{name_pascal}Agent", "{name_pascal}Input", "{name_pascal}Result"]

test_source MUST:
- use DummyLLMProvider (no network calls)
- assert result.approved is False when any BLOCKER present

pipeline_entry: a YAML snippet `agent: {name}` suitable for .agent-pipeline.yml.
runner_source: minimal scripts/run_{name}.py with argparse and --out flag.
"""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RuleSpec(BaseModel):
    rule_id: str
    severity: str
    trigger: str


class FieldSpec(BaseModel):
    name: str
    type: str
    required: bool = True
    description: str = ""


class NewAgentInput(BaseModel):
    name: str  # snake_case
    description: str
    rules: List[Dict[str, Any]]
    input_fields: List[Dict[str, Any]]
    trigger: str


class NewAgentResult(BaseModel):
    agent_source: str
    runner_source: str
    test_source: str
    pipeline_entry: str
    review_findings: List[Finding]
    approved: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_pascal(snake: str) -> str:
    return "".join(word.capitalize() for word in snake.split("_"))


def _parse_scaffold(text: str) -> Optional[Dict[str, str]]:
    """Parse the JSON scaffold response from the LLM."""
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("NewAgentAgent: could not parse scaffold JSON")
        return None

    required = {"agent_source", "runner_source", "test_source", "pipeline_entry"}
    if not required.issubset(data.keys()):
        logger.warning("NewAgentAgent: scaffold JSON missing required fields")
        return None
    return {k: str(data[k]) for k in required}


def _fallback_scaffold(name: str) -> Dict[str, str]:
    """Return a minimal skeleton scaffold when LLM fails."""
    pascal = _to_pascal(name)
    return {
        "agent_source": (
            f'"""agent_sdlc/agents/{name}.py — generated scaffold."""\n'
            "from __future__ import annotations\n"
            "from typing import List\n"
            "from pydantic import BaseModel\n"
            "from agent_sdlc.core.findings import Finding, FindingSeverity\n"
            "from agent_sdlc.core.providers import ProviderProtocol\n\n"
            f"class {pascal}Input(BaseModel):\n    text: str\n\n"
            f"class {pascal}Result(BaseModel):\n    findings: List[Finding]\n    approved: bool\n\n"
            f"class {pascal}Agent:\n"
            "    def __init__(self, provider: ProviderProtocol) -> None:\n"
            "        self.provider = provider\n\n"
            f"    def run(self, inp: {pascal}Input) -> {pascal}Result:\n"
            "        return {pascal}Result(findings=[], approved=True)\n\n"
            f'__all__ = ["{pascal}Agent", "{pascal}Input", "{pascal}Result"]\n'
        ),
        "runner_source": f'"""scripts/run_{name}.py — generated runner."""\n',
        "test_source": (
            f"from agent_sdlc.agents.{name} import {pascal}Agent, {pascal}Input\n"
            "from agent_sdlc.core.providers import DummyLLMProvider\n\n"
            f"def test_{name}_runs():\n"
            f"    result = {pascal}Agent(DummyLLMProvider()).run({pascal}Input(text='x'))\n"
            "    assert isinstance(result.approved, bool)\n"
        ),
        "pipeline_entry": f"agent: {name}\n  on_failure: continue\n",
    }


# ---------------------------------------------------------------------------
# NewAgentAgent
# ---------------------------------------------------------------------------


class NewAgentAgent:
    """Scaffolds a new pattern-compliant agent and validates it before shipping."""

    def __init__(self, provider: ProviderProtocol) -> None:
        self.provider = provider

    def run(self, inp: NewAgentInput) -> NewAgentResult:
        pascal = _to_pascal(inp.name)

        rules_block = "\n".join(
            f"- {r.get('rule_id', '?')} [{r.get('severity', '?').upper()}]: "
            f"{r.get('trigger', '')}"
            for r in inp.rules
        )
        fields_block = "\n".join(
            f"- {f.get('name', '?')}: {f.get('type', 'str')} "
            f"({'required' if f.get('required', True) else 'optional'}) — "
            f"{f.get('description', '')}"
            for f in inp.input_fields
        )

        prompt = _SCAFFOLD_PROMPT.format(
            name=inp.name,
            name_pascal=pascal,
            description=inp.description,
            trigger=inp.trigger,
            rules_block=rules_block or "(none specified)",
            fields_block=fields_block or "(none specified)",
        )

        scaffold: Optional[Dict[str, str]] = None
        try:
            response = self.provider.complete(prompt)
            scaffold = _parse_scaffold(response.content)
        except Exception as exc:
            logger.warning("NewAgentAgent: LLM call failed — %s; using fallback", exc)

        if scaffold is None:
            logger.info("NewAgentAgent: using fallback scaffold for '%s'", inp.name)
            scaffold = _fallback_scaffold(inp.name)

        # Validate generated code with AgentReviewAgent
        review_findings: List[Finding] = []
        approved = False
        try:
            from agent_sdlc.agents.agent_review import (
                AgentReviewAgent,
                AgentReviewInput,
            )

            reviewer = AgentReviewAgent()
            review_result = reviewer.run(
                AgentReviewInput(
                    agent_source=scaffold["agent_source"],
                    test_source=scaffold["test_source"],
                    agent_name=inp.name,
                    runner_source=scaffold["runner_source"],
                    pipeline_entry=scaffold["pipeline_entry"],
                )
            )
            review_findings = review_result.findings
            approved = review_result.approved
        except Exception as exc:
            logger.warning("NewAgentAgent: AgentReviewAgent failed — %s", exc)

        return NewAgentResult(
            agent_source=scaffold["agent_source"],
            runner_source=scaffold["runner_source"],
            test_source=scaffold["test_source"],
            pipeline_entry=scaffold["pipeline_entry"],
            review_findings=review_findings,
            approved=approved,
        )


__all__ = ["NewAgentAgent", "NewAgentInput", "NewAgentResult"]
