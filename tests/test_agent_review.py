"""Tests for AgentReviewAgent — pattern compliance checks for new agents."""

from agent_sdlc.agents.agent_review import (
    AgentReviewAgent,
    AgentReviewInput,
)
from agent_sdlc.core.findings import FindingSeverity


# ---------------------------------------------------------------------------
# Good agent source (passes all checks)
# ---------------------------------------------------------------------------

GOOD_AGENT = '''\
from agent_sdlc.core.providers import ProviderProtocol
from agent_sdlc.core.findings import Finding, FindingSeverity

class GoodAgent:
    def __init__(self, provider: ProviderProtocol) -> None:
        self.provider = provider

    def run(self):
        return Finding(severity=FindingSeverity.BLOCKER, message="x", rule="Good:x")

__all__ = ["GoodAgent"]
'''

GOOD_TEST = '''\
def test_blocker_sets_approved_false():
    result = run_agent()
    assert result.approved is False
'''

PIPELINE_YAML = '''\
pipelines:
  pr:
    steps:
      - agent: good_agent
'''


# ---------------------------------------------------------------------------
# Tests: BLOCKER rules
# ---------------------------------------------------------------------------


def test_missing_all_export_is_blocker():
    source = "class MyAgent: pass"  # no __all__
    inp = AgentReviewInput(
        agent_name="my_agent", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    assert result.approved is False
    blocker_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER]
    assert "AgentReview:export" in blocker_rules


def test_direct_sdk_import_is_blocker():
    source = '''\
import anthropic
__all__ = ["Bad"]
'''
    inp = AgentReviewInput(
        agent_name="bad", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    assert result.approved is False
    blocker_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER]
    assert "AgentReview:no-direct-sdk" in blocker_rules


def test_from_openai_import_is_blocker():
    source = '''\
from openai import OpenAI
__all__ = ["Bad"]
'''
    inp = AgentReviewInput(
        agent_name="bad", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    blocker_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER]
    assert "AgentReview:no-direct-sdk" in blocker_rules


def test_no_test_file_is_blocker():
    inp = AgentReviewInput(
        agent_name="my_agent", source_code=GOOD_AGENT, test_code=None
    )
    result = AgentReviewAgent().run(inp)
    assert result.approved is False
    blocker_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER]
    assert "AgentReview:test-exists" in blocker_rules


def test_missing_blocker_test_is_blocker():
    source = '''\
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol

class Agent:
    def run(self):
        return Finding(severity="blocker", message="x")

__all__ = ["Agent"]
'''
    test_code = "def test_something():\n    assert 1 == 1"
    inp = AgentReviewInput(
        agent_name="agent", source_code=source, test_code=test_code
    )
    result = AgentReviewAgent().run(inp)
    blocker_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER]
    assert "AgentReview:blocker-test" in blocker_rules


# ---------------------------------------------------------------------------
# Tests: WARNING rules
# ---------------------------------------------------------------------------


def test_no_finding_schema_is_warning():
    source = '''\
from agent_sdlc.core.providers import ProviderProtocol

class Agent:
    pass

__all__ = ["Agent"]
'''
    inp = AgentReviewInput(
        agent_name="agent", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    warning_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.WARNING]
    assert "AgentReview:finding-schema" in warning_rules


def test_no_provider_protocol_is_warning():
    source = '''\
from agent_sdlc.core.findings import Finding

class Agent:
    pass

__all__ = ["Agent"]
'''
    inp = AgentReviewInput(
        agent_name="agent", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    warning_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.WARNING]
    assert "AgentReview:provider-protocol" in warning_rules


def test_missing_pipeline_yaml_is_warning():
    inp = AgentReviewInput(
        agent_name="agent",
        source_code=GOOD_AGENT,
        test_code=GOOD_TEST,
        pipeline_yaml=None,
    )
    result = AgentReviewAgent().run(inp)
    warning_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.WARNING]
    assert "AgentReview:pipeline-wiring" in warning_rules


def test_agent_not_in_pipeline_is_warning():
    inp = AgentReviewInput(
        agent_name="unknown_agent",
        source_code=GOOD_AGENT,
        test_code=GOOD_TEST,
        pipeline_yaml=PIPELINE_YAML,
    )
    result = AgentReviewAgent().run(inp)
    warning_rules = [f.rule for f in result.findings if f.severity == FindingSeverity.WARNING]
    assert "AgentReview:pipeline-wiring" in warning_rules


# ---------------------------------------------------------------------------
# Tests: passing review
# ---------------------------------------------------------------------------


def test_good_agent_passes_review():
    inp = AgentReviewInput(
        agent_name="good_agent",
        source_code=GOOD_AGENT,
        test_code=GOOD_TEST,
        pipeline_yaml=PIPELINE_YAML,
    )
    result = AgentReviewAgent().run(inp)
    assert result.approved is True
    assert result.blocker_count == 0


def test_findings_sorted_blockers_first():
    source = "class Agent: pass"  # no __all__, no Finding, no ProviderProtocol
    inp = AgentReviewInput(
        agent_name="agent", source_code=source, test_code="def test(): pass"
    )
    result = AgentReviewAgent().run(inp)
    severities = [f.severity for f in result.findings]
    for i in range(len(severities) - 1):
        assert severities[i].value <= severities[i + 1].value or \
            severities[i] == FindingSeverity.BLOCKER
