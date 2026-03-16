"""Unit tests for Pipeline Orchestrator.

All subprocess calls and filesystem I/O are mocked — zero network calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.run_pipeline import (
    _execute_step,
    _paths_match,
    _run_agent,
    load_pipeline_config,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Minimal pipeline YAML fixture
# ---------------------------------------------------------------------------

_MINIMAL_YAML = """\
pipelines:
  pull_request:
    steps:
      - parallel:
          - agent: pr_review
            on_failure: continue
          - agent: prompt_review
            paths: ["agent_sdlc/agents/**"]
            on_failure: continue
      - always:
          - agent: finding_aggregator
  issues_opened:
    steps:
      - sequential:
          - agent: product_owner
            on_failure: abort
          - agent: issue_refinement
            on_failure: continue
"""


@pytest.fixture()
def pipeline_cfg(tmp_path):
    cfg_file = tmp_path / ".agent-pipeline.yml"
    cfg_file.write_text(_MINIMAL_YAML)
    return str(cfg_file)


# ---------------------------------------------------------------------------
# _paths_match
# ---------------------------------------------------------------------------


def test_paths_match_returns_true_when_file_matches():
    assert _paths_match(["agent_sdlc/agents/**"], ["agent_sdlc/agents/pr_review.py"])


def test_paths_match_returns_false_when_no_file_matches():
    assert not _paths_match(["agent_sdlc/agents/**"], ["scripts/run_pr_review.py"])


def test_paths_match_returns_true_when_no_changed_files():
    # If changed-file info is unavailable, don't skip
    assert _paths_match(["agent_sdlc/agents/**"], [])


# ---------------------------------------------------------------------------
# _run_agent — mocked subprocess
# ---------------------------------------------------------------------------


def _fake_findings():
    return [
        {"severity": "warning", "rule": "test:rule", "location": "x.py", "message": "m"}
    ]


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_run_agent_returns_findings_on_success(tmp_path):
    findings = _fake_findings()

    def fake_run(cmd, **kwargs):
        # Write findings to the --out file
        idx = cmd.index("--out")
        with open(cmd[idx + 1], "w") as fh:
            json.dump(findings, fh)
        return _make_proc(returncode=0)

    agent_cfg = {"agent": "pr_review", "on_failure": "continue"}
    with (
        patch(
            "scripts.run_pipeline._AGENT_RUNNERS",
            {"pr_review": "scripts/run_pr_review.py"},
        ),
        patch("os.path.exists", return_value=True),
        patch("subprocess.run", side_effect=fake_run),
    ):
        name, success, result = _run_agent(
            agent_cfg, pr_number=1, issue_number=None, changed_files=[]
        )

    assert success is True
    assert name == "pr_review"
    assert len(result) == 1
    assert result[0]["rule"] == "test:rule"


def test_run_agent_skipped_when_paths_no_match():
    agent_cfg = {
        "agent": "prompt_review",
        "paths": ["agent_sdlc/agents/**"],
        "on_failure": "continue",
    }
    with patch("subprocess.run") as mock_sp:
        name, success, findings = _run_agent(
            agent_cfg,
            pr_number=1,
            issue_number=None,
            changed_files=["scripts/run_pr_review.py"],
        )

    mock_sp.assert_not_called()
    assert success is True
    assert findings == []


def test_run_agent_unknown_runner_skipped():
    agent_cfg = {"agent": "nonexistent_agent", "on_failure": "continue"}
    with patch("subprocess.run") as mock_sp:
        name, success, findings = _run_agent(
            agent_cfg, pr_number=None, issue_number=None, changed_files=[]
        )

    mock_sp.assert_not_called()
    assert success is True
    assert findings == []


# ---------------------------------------------------------------------------
# _execute_step
# ---------------------------------------------------------------------------


def _patched_run_agent_success(agent_cfg, pr_number, issue_number, changed_files):
    return agent_cfg["agent"], True, _fake_findings()


def _patched_run_agent_failure(agent_cfg, pr_number, issue_number, changed_files):
    return agent_cfg["agent"], False, []


def test_parallel_step_runs_all_agents():
    step = {
        "parallel": [
            {"agent": "pr_review", "on_failure": "continue"},
            {"agent": "prompt_review", "on_failure": "continue"},
        ]
    }
    with patch(
        "scripts.run_pipeline._run_agent", side_effect=_patched_run_agent_success
    ):
        aborted, findings = _execute_step(
            step, pr_number=1, issue_number=None, changed_files=[]
        )

    assert not aborted
    assert "pr_review" in findings
    assert "prompt_review" in findings


def test_abort_on_failure_stops_sequential_pipeline():
    step = {
        "sequential": [
            {"agent": "product_owner", "on_failure": "abort"},
            {"agent": "issue_refinement", "on_failure": "continue"},
        ]
    }
    called = []

    def fake_run(cfg, pr_number, issue_number, changed_files):
        called.append(cfg["agent"])
        if cfg["agent"] == "product_owner":
            return "product_owner", False, []
        return cfg["agent"], True, _fake_findings()

    with patch("scripts.run_pipeline._run_agent", side_effect=fake_run):
        aborted, findings = _execute_step(
            step, pr_number=None, issue_number=1, changed_files=[]
        )

    assert aborted is True
    assert "issue_refinement" not in called  # second agent never ran


def test_findings_from_all_agents_reach_aggregator(pipeline_cfg):
    """All agent findings are collected and available after run_pipeline."""
    findings_by_agent = {}

    def fake_run_agent(cfg, pr_number, issue_number, changed_files):
        name = cfg["agent"]
        findings = _fake_findings() if name != "finding_aggregator" else []
        findings_by_agent[name] = findings
        return name, True, findings

    with (
        patch("scripts.run_pipeline._run_agent", side_effect=fake_run_agent),
        patch(
            "scripts.run_pipeline._get_changed_files",
            return_value=["agent_sdlc/agents/x.py"],
        ),
    ):
        aborted, results = run_pipeline(
            trigger="pull_request",
            pr_number=1,
            config_path=pipeline_cfg,
        )

    assert not aborted
    # All three agents (pr_review, prompt_review, finding_aggregator) were invoked
    assert "pr_review" in results
    assert "finding_aggregator" in results


# ---------------------------------------------------------------------------
# load_pipeline_config
# ---------------------------------------------------------------------------


def test_load_pipeline_config_parses_yaml(pipeline_cfg):
    config = load_pipeline_config(pipeline_cfg)
    assert "pipelines" in config
    assert "pull_request" in config["pipelines"]
    assert "issues_opened" in config["pipelines"]


def test_run_pipeline_unknown_trigger_returns_empty(pipeline_cfg):
    aborted, findings = run_pipeline(
        trigger="issues_labeled_bug",
        config_path=pipeline_cfg,
    )
    assert not aborted
    assert findings == {}
