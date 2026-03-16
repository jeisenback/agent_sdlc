"""Tests for PipelineOrchestrator — YAML-driven multi-agent coordination."""

from pathlib import Path
from typing import List, Optional

import pytest

from agent_sdlc.agents.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineConfig,
    PipelineEvent,
    load_pipeline_config,
)
from agent_sdlc.core.findings import Finding, FindingSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

YAML_CONTENT = """\
pipelines:
  pull_request:
    triggers:
      - event: pull_request
        actions: [opened, synchronize]
    steps:
      - parallel:
          - agent: pr_review
          - agent: arch_review
            on_failure: continue
      - sequential:
          - agent: reasoning_check
            consumes_upstream: true
            trigger_on: blocker_present
            on_failure: continue
      - always:
          - agent: finding_aggregator

  issue:
    triggers:
      - event: issues
        actions: [opened]
    steps:
      - parallel:
          - agent: issue_refinement
      - always:
          - agent: finding_aggregator
"""


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / ".agent-pipeline.yml"
    config_path.write_text(YAML_CONTENT)
    return config_path


def _dummy_runner(
    responses: Optional[dict] = None,
):
    """Returns an agent_runner that returns canned findings per agent name."""
    responses = responses or {}

    def runner(
        agent_name: str, mode: Optional[str], upstream: List[Finding]
    ) -> tuple:
        if agent_name in responses:
            return responses[agent_name]
        return ([], 0)

    return runner


def _blocker_finding(rule: str = "test:blocker") -> Finding:
    return Finding(
        rule=rule, location="x.py", severity=FindingSeverity.BLOCKER, message="block"
    )


def _warning_finding(rule: str = "test:warn") -> Finding:
    return Finding(
        rule=rule, location="x.py", severity=FindingSeverity.WARNING, message="warn"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_pipeline_config(tmp_path: Path):
    config_path = _write_config(tmp_path)
    config = load_pipeline_config(config_path)
    assert "pull_request" in config.pipelines
    assert "issue" in config.pipelines
    pr_pipeline = config.pipelines["pull_request"]
    assert len(pr_pipeline.steps) == 3
    assert pr_pipeline.steps[0].step_type == "parallel"


def test_match_pipeline_pr_event(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    orch = PipelineOrchestrator(config, _dummy_runner())
    event = PipelineEvent(event="pull_request", action="opened")
    matched = orch.match_pipeline(event)
    assert matched is not None
    assert matched.name == "pull_request"


def test_match_pipeline_issue_event(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    orch = PipelineOrchestrator(config, _dummy_runner())
    event = PipelineEvent(event="issues", action="opened")
    matched = orch.match_pipeline(event)
    assert matched is not None
    assert matched.name == "issue"


def test_no_match_returns_none(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    orch = PipelineOrchestrator(config, _dummy_runner())
    event = PipelineEvent(event="push", action="")
    assert orch.match_pipeline(event) is None
    assert orch.run(event) is None


def test_run_pr_pipeline_no_findings(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    orch = PipelineOrchestrator(config, _dummy_runner())
    event = PipelineEvent(event="pull_request", action="opened")
    result = orch.run(event, pipeline_run_id="run-1")
    assert result is not None
    assert result.pipeline_name == "pull_request"
    assert result.aggregated.approved is True
    assert result.aggregated.findings == []
    assert result.aborted is False


def test_run_pr_pipeline_with_blockers(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    runner = _dummy_runner(
        responses={
            "pr_review": ([_blocker_finding("code:bad")], 0),
        }
    )
    orch = PipelineOrchestrator(config, runner)
    event = PipelineEvent(event="pull_request", action="opened")
    result = orch.run(event)
    assert result is not None
    assert result.aggregated.approved is False
    assert result.aggregated.blocker_count == 1


def test_reasoning_check_skipped_when_no_blockers(tmp_path: Path):
    """reasoning_check has trigger_on=blocker_present; should be skipped with no blockers."""
    config = load_pipeline_config(_write_config(tmp_path))
    called_agents = []

    def tracking_runner(name, mode, upstream):
        called_agents.append(name)
        return ([], 0)

    orch = PipelineOrchestrator(config, tracking_runner)
    event = PipelineEvent(event="pull_request", action="opened")
    orch.run(event)
    assert "reasoning_check" not in called_agents


def test_reasoning_check_runs_when_blockers_present(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    called_agents = []

    def tracking_runner(name, mode, upstream):
        called_agents.append(name)
        if name == "pr_review":
            return ([_blocker_finding()], 0)
        return ([], 0)

    orch = PipelineOrchestrator(config, tracking_runner)
    event = PipelineEvent(event="pull_request", action="opened")
    orch.run(event)
    assert "reasoning_check" in called_agents


def test_agent_failure_continue(tmp_path: Path):
    """Agent with on_failure=continue should not abort the pipeline."""
    config = load_pipeline_config(_write_config(tmp_path))
    runner = _dummy_runner(
        responses={
            "arch_review": ([], 1),  # fails but on_failure=continue
        }
    )
    orch = PipelineOrchestrator(config, runner)
    event = PipelineEvent(event="pull_request", action="opened")
    result = orch.run(event)
    assert result is not None
    assert result.aborted is False
    assert "arch_review" in result.aggregated.agents_failed


def test_agent_failure_abort(tmp_path: Path):
    """Agent with on_failure=abort should stop the pipeline."""
    yaml_abort = """\
pipelines:
  test:
    triggers:
      - event: test
        actions: [run]
    steps:
      - sequential:
          - agent: strict_agent
            on_failure: abort
          - agent: after_agent
      - always:
          - agent: finding_aggregator
"""
    config_path = tmp_path / ".agent-pipeline.yml"
    config_path.write_text(yaml_abort)
    config = load_pipeline_config(config_path)

    called_agents = []

    def tracking_runner(name, mode, upstream):
        called_agents.append(name)
        if name == "strict_agent":
            return ([], 1)
        return ([], 0)

    orch = PipelineOrchestrator(config, tracking_runner)
    event = PipelineEvent(event="test", action="run")
    result = orch.run(event)
    assert result is not None
    assert result.aborted is True
    assert "after_agent" not in called_agents


def test_agent_exception_handled(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))

    def crashing_runner(name, mode, upstream):
        if name == "pr_review":
            raise RuntimeError("boom")
        return ([], 0)

    orch = PipelineOrchestrator(config, crashing_runner)
    event = PipelineEvent(event="pull_request", action="opened")
    result = orch.run(event)
    assert result is not None
    # pr_review crashed but pipeline continues (on_failure default = continue)
    assert "pr_review" in result.aggregated.agents_failed


def test_path_matching(tmp_path: Path):
    yaml_paths = """\
pipelines:
  agent_review:
    triggers:
      - event: pull_request
        actions: [opened]
        paths:
          - "agent_sdlc/agents/**"
    steps:
      - sequential:
          - agent: agent_review
      - always:
          - agent: finding_aggregator
"""
    config_path = tmp_path / ".agent-pipeline.yml"
    config_path.write_text(yaml_paths)
    config = load_pipeline_config(config_path)
    orch = PipelineOrchestrator(config, _dummy_runner())

    # Matching path
    event_match = PipelineEvent(
        event="pull_request",
        action="opened",
        changed_paths=["agent_sdlc/agents/new_agent.py"],
    )
    assert orch.match_pipeline(event_match) is not None

    # Non-matching path
    event_no_match = PipelineEvent(
        event="pull_request",
        action="opened",
        changed_paths=["agent_sdlc/core/retry.py"],
    )
    assert orch.match_pipeline(event_no_match) is None


def test_pipeline_run_id_propagated(tmp_path: Path):
    config = load_pipeline_config(_write_config(tmp_path))
    orch = PipelineOrchestrator(config, _dummy_runner())
    event = PipelineEvent(event="pull_request", action="opened")
    result = orch.run(event, pipeline_run_id="abc-123")
    assert result.aggregated.pipeline_run_id == "abc-123"
