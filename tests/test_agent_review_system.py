"""Unit tests for AgentReviewAgent system mode.

DummyLLMProvider only — zero network calls.
"""

from __future__ import annotations

from agent_sdlc.agents.agent_review import AgentReviewAgent, SystemReviewInput
from agent_sdlc.core.findings import FindingSeverity

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_PIPELINE_WITH_AGGREGATOR = """\
pipelines:
  pull_request:
    steps:
      - parallel:
          - agent: agent_a
      - always:
          - agent: finding_aggregator
"""

_PIPELINE_WITHOUT_AGGREGATOR = """\
pipelines:
  pull_request:
    steps:
      - parallel:
          - agent: agent_a
"""

_SOURCE_A = """\
from agent_sdlc.core.findings import Finding, FindingSeverity
rule = "MyNS:some-rule"
approved = True
__all__ = ["AgentA"]
"""

_SOURCE_B_SAME_NS = """\
from agent_sdlc.core.findings import Finding, FindingSeverity
rule = "MyNS:other-rule"
approved = True
__all__ = ["AgentB"]
"""

_SOURCE_B_DIFF_NS = """\
from agent_sdlc.core.findings import Finding, FindingSeverity
rule = "OtherNS:some-rule"
approved = True
__all__ = ["AgentB"]
"""


def _run(agent_sources, pipeline_config=_PIPELINE_WITH_AGGREGATOR, namespaces=None):
    inp = SystemReviewInput(
        agent_sources=agent_sources,
        pipeline_config=pipeline_config,
        finding_namespaces=namespaces or [],
    )
    return AgentReviewAgent().run_system(inp)


# ---------------------------------------------------------------------------
# AC 1: two agents with same namespace prefix → namespace-collision BLOCKER
# ---------------------------------------------------------------------------


def test_namespace_collision_detected_as_blocker():
    result = _run({"agent_a": _SOURCE_A, "agent_b": _SOURCE_B_SAME_NS})
    rules = [f.rule for f in result.findings]
    assert "AgentReview:sys:namespace-collision" in rules
    assert result.approved is False


def test_different_namespaces_no_collision():
    result = _run({"agent_a": _SOURCE_A, "agent_b": _SOURCE_B_DIFF_NS})
    collision_rules = [
        f.rule
        for f in result.findings
        if f.rule == "AgentReview:sys:namespace-collision"
    ]
    assert collision_rules == []


# ---------------------------------------------------------------------------
# AC 2: agent in source dir but not in pipeline YAML → orphan-agent WARNING
# ---------------------------------------------------------------------------


def test_orphan_agent_warning_when_not_in_pipeline():
    result = _run(
        {"agent_a": _SOURCE_A, "orphan_agent": _SOURCE_B_DIFF_NS},
        pipeline_config=_PIPELINE_WITH_AGGREGATOR,
    )
    rules = [f.rule for f in result.findings]
    assert "AgentReview:sys:orphan-agent" in rules
    # WARNING — should not affect approved when no BLOCKERs from other rules
    orphan_findings = [
        f for f in result.findings if f.rule == "AgentReview:sys:orphan-agent"
    ]
    assert all(f.severity == FindingSeverity.WARNING for f in orphan_findings)


def test_no_orphan_when_all_agents_in_pipeline():
    result = _run(
        {"agent_a": _SOURCE_A},
        pipeline_config=_PIPELINE_WITH_AGGREGATOR,
    )
    orphan_rules = [f.rule for f in result.findings if "orphan" in f.rule]
    assert orphan_rules == []


# ---------------------------------------------------------------------------
# no-aggregation rule
# ---------------------------------------------------------------------------


def test_no_aggregation_warning_when_absent_from_pipeline():
    result = _run(
        {"agent_a": _SOURCE_A},
        pipeline_config=_PIPELINE_WITHOUT_AGGREGATOR,
    )
    rules = [f.rule for f in result.findings]
    assert "AgentReview:sys:no-aggregation" in rules


def test_no_aggregation_not_raised_when_aggregator_present():
    result = _run(
        {"agent_a": _SOURCE_A},
        pipeline_config=_PIPELINE_WITH_AGGREGATOR,
    )
    agg_rules = [
        f.rule for f in result.findings if f.rule == "AgentReview:sys:no-aggregation"
    ]
    assert agg_rules == []


# ---------------------------------------------------------------------------
# inconsistent-gate rule
# ---------------------------------------------------------------------------


def test_inconsistent_gate_warning_when_mixed_names():
    source_passed = _SOURCE_A.replace("approved", "passed")
    result = _run({"agent_a": _SOURCE_A, "agent_b": source_passed})
    rules = [f.rule for f in result.findings]
    assert "AgentReview:sys:inconsistent-gate" in rules


def test_no_inconsistent_gate_when_single_name():
    result = _run({"agent_a": _SOURCE_A, "agent_b": _SOURCE_B_DIFF_NS})
    gate_rules = [f.rule for f in result.findings if "inconsistent-gate" in f.rule]
    assert gate_rules == []


# ---------------------------------------------------------------------------
# Empty catalog
# ---------------------------------------------------------------------------


def test_empty_catalog_passes():
    result = _run({})
    # coverage-gap warnings will fire for empty catalog but no BLOCKERs
    assert result.approved is True
