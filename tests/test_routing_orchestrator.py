"""Unit tests for RoutingOrchestrator.

DummyLLMProvider only — zero network calls.
"""

from __future__ import annotations

import json
import os

import pytest

from agent_sdlc.agents.routing_orchestrator import (
    RoutingInput,
    RoutingOrchestrator,
    RoutingPlan,
)
from agent_sdlc.core.providers import DummyLLMProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_YAML_PIPELINE = """\
pipelines:
  pull_request:
    steps:
      - parallel:
          - agent: pr_review
            on_failure: continue
          - agent: prompt_review
            on_failure: continue
      - always:
          - agent: finding_aggregator
  issues_opened:
    steps:
      - sequential:
          - agent: issue_refinement
            on_failure: continue
"""

_AVAILABLE = [
    "pr_review",
    "prompt_review",
    "arch_review",
    "finding_aggregator",
    "issue_refinement",
]


@pytest.fixture()
def yaml_config(tmp_path):
    cfg = tmp_path / ".agent-pipeline.yml"
    cfg.write_text(_YAML_PIPELINE)
    return str(cfg)


@pytest.fixture()
def log_path(tmp_path):
    return str(tmp_path / "routing_log.json")


def _input(**kwargs):
    defaults = dict(
        trigger="pull_request",
        context="Code changes in agent_sdlc/agents/",
        changed_files=["agent_sdlc/agents/pr_review.py"],
        labels=[],
        available_agents=_AVAILABLE,
    )
    defaults.update(kwargs)
    return RoutingInput(**defaults)


# ---------------------------------------------------------------------------
# Fallback path (DummyLLMProvider returns non-JSON → fallback used)
# ---------------------------------------------------------------------------


def test_fallback_produces_valid_routing_plan(yaml_config, log_path):
    """DummyLLMProvider returns 'OK' (non-JSON) → fallback to YAML config."""
    provider = DummyLLMProvider(default="OK")
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(_input())

    assert isinstance(plan, RoutingPlan)
    assert plan.fallback_used is True
    assert len(plan.steps) > 0
    assert "Fallback" in plan.rationale


def test_fallback_sets_fallback_used_true(yaml_config, log_path):
    provider = DummyLLMProvider(default="not json")
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(_input())
    assert plan.fallback_used is True


def test_fallback_unknown_trigger_returns_empty_steps(yaml_config, log_path):
    provider = DummyLLMProvider(default="bad")
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(_input(trigger="unknown_trigger"))
    assert plan.fallback_used is True
    assert plan.steps == []


# ---------------------------------------------------------------------------
# LLM path (DummyLLMProvider returns valid routing JSON)
# ---------------------------------------------------------------------------


def _llm_response(agents_parallel, rationale="LLM selected"):
    return json.dumps(
        {
            "steps": [{"parallel": agents_parallel}],
            "rationale": rationale,
        }
    )


def test_llm_path_produces_plan_with_fallback_false(yaml_config, log_path):
    response = _llm_response(["pr_review", "finding_aggregator"])
    provider = DummyLLMProvider(default=response)
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(_input())

    assert plan.fallback_used is False
    assert len(plan.steps) > 0


def test_llm_path_filters_unknown_agents(yaml_config, log_path):
    """Agents not in available_agents list are filtered out."""
    response = _llm_response(["pr_review", "nonexistent_agent"])
    provider = DummyLLMProvider(default=response)
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(_input())

    assert plan.fallback_used is False
    # nonexistent_agent filtered; pr_review kept
    agents_in_plan = [
        a["agent"]
        for step in plan.steps
        for agents in step.values()
        if isinstance(agents, list)
        for a in agents
        if isinstance(a, dict)
    ]
    assert "nonexistent_agent" not in agents_in_plan
    assert "pr_review" in agents_in_plan


# ---------------------------------------------------------------------------
# Routing log written
# ---------------------------------------------------------------------------


def test_routing_log_written_to_file(yaml_config, log_path):
    provider = DummyLLMProvider(default="bad")
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    orchestrator.run(_input())

    assert os.path.exists(log_path)
    with open(log_path) as fh:
        log = json.load(fh)
    assert "rationale" in log
    assert "fallback_used" in log


# ---------------------------------------------------------------------------
# Integration test stub
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_integration_docs_only_pr_skips_arch_review(yaml_config, log_path):
    """Docs-only PR → arch_review and prompt_review absent from plan."""
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    from agent_sdlc.core.providers import AnthropicProvider

    provider = AnthropicProvider(api_key=api_key)
    orchestrator = RoutingOrchestrator(
        provider=provider, config_path=yaml_config, log_path=log_path
    )
    plan = orchestrator.run(
        _input(
            changed_files=["docs/README.md", "docs/design.md"],
            context="Documentation update only — no code changes",
        )
    )

    agents_in_plan = [
        a["agent"]
        for step in plan.steps
        for agents in step.values()
        if isinstance(agents, list)
        for a in agents
        if isinstance(a, dict)
    ]
    assert "arch_review" not in agents_in_plan
    assert "prompt_review" not in agents_in_plan
