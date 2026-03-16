"""Unit tests for NewAgentAgent.

DummyLLMProvider only — zero network calls.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from agent_sdlc.agents.new_agent import NewAgentAgent, NewAgentInput
from agent_sdlc.core.providers import DummyLLMProvider

# ---------------------------------------------------------------------------
# Canned scaffold that passes AgentReviewAgent BLOCKER checks
# ---------------------------------------------------------------------------

_VALID_AGENT_SOURCE = '''\
"""agent_sdlc/agents/sample_check.py — generated scaffold."""
from __future__ import annotations
from typing import List
from pydantic import BaseModel
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol

class SampleCheckInput(BaseModel):
    text: str

class SampleCheckResult(BaseModel):
    findings: List[Finding]
    approved: bool

class SampleCheckAgent:
    def __init__(self, provider: ProviderProtocol) -> None:
        self.provider = provider

    def run(self, inp: SampleCheckInput) -> SampleCheckResult:
        findings = []
        if not inp.text:
            findings.append(Finding(
                severity=FindingSeverity.BLOCKER,
                rule="sample:missing-text",
                message="Text is empty.",
            ))
        approved = all(f.severity != FindingSeverity.BLOCKER for f in findings)
        return SampleCheckResult(findings=findings, approved=approved)

__all__ = ["SampleCheckAgent", "SampleCheckInput", "SampleCheckResult"]
'''

_VALID_TEST_SOURCE = """\
from agent_sdlc.agents.sample_check import SampleCheckAgent, SampleCheckInput
from agent_sdlc.core.providers import DummyLLMProvider

def test_blocker_when_empty():
    result = SampleCheckAgent(DummyLLMProvider()).run(SampleCheckInput(text=""))
    assert result.approved is False
"""

_CANNED_SCAFFOLD = json.dumps(
    {
        "agent_source": _VALID_AGENT_SOURCE,
        "runner_source": "# runner\n",
        "test_source": _VALID_TEST_SOURCE,
        "pipeline_entry": "agent: sample_check\n  on_failure: continue\n",
    }
)


def _inp(**kwargs):
    defaults = dict(
        name="sample_check",
        description="A sample check agent",
        rules=[
            {"rule_id": "sample:rule", "severity": "blocker", "trigger": "text empty"}
        ],
        input_fields=[
            {"name": "text", "type": "str", "required": True, "description": "input"}
        ],
        trigger="pull_request",
    )
    defaults.update(kwargs)
    return NewAgentInput(**defaults)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_agent_source_contains_provider_protocol_and_all():
    provider = DummyLLMProvider(default=_CANNED_SCAFFOLD)
    result = NewAgentAgent(provider=provider).run(_inp())

    assert "ProviderProtocol" in result.agent_source
    assert "__all__" in result.agent_source


def test_review_findings_is_list():
    provider = DummyLLMProvider(default=_CANNED_SCAFFOLD)
    result = NewAgentAgent(provider=provider).run(_inp())

    assert isinstance(result.review_findings, list)


def test_agent_review_agent_is_called():
    """AgentReviewAgent.run() is invoked during scaffold validation."""
    provider = DummyLLMProvider(default=_CANNED_SCAFFOLD)
    with patch(
        "agent_sdlc.agents.agent_review.AgentReviewAgent.run",
        wraps=__import__(
            "agent_sdlc.agents.agent_review", fromlist=["AgentReviewAgent"]
        )
        .AgentReviewAgent()
        .run,
    ) as mock_run:
        NewAgentAgent(provider=provider).run(_inp())
        assert mock_run.call_count >= 1


def test_fallback_scaffold_used_when_llm_returns_invalid_json():
    provider = DummyLLMProvider(default="not json at all")
    result = NewAgentAgent(provider=provider).run(_inp())

    # Fallback scaffold always contains ProviderProtocol and __all__
    assert "ProviderProtocol" in result.agent_source
    assert "__all__" in result.agent_source
    assert isinstance(result.review_findings, list)


def test_valid_scaffold_passes_agent_review():
    """A well-formed scaffold returns approved=True."""
    provider = DummyLLMProvider(default=_CANNED_SCAFFOLD)
    result = NewAgentAgent(provider=provider).run(_inp())

    assert result.approved is True


def test_all_four_files_populated():
    provider = DummyLLMProvider(default=_CANNED_SCAFFOLD)
    result = NewAgentAgent(provider=provider).run(_inp())

    assert result.agent_source
    assert result.runner_source
    assert result.test_source
    assert result.pipeline_entry


@pytest.mark.integration
def test_integration_generate_one_rule_agent(tmp_path):
    """Generate a 1-rule WARNING agent end-to-end with real LLM."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    from agent_sdlc.core.providers import AnthropicProvider

    provider = AnthropicProvider()
    agent = NewAgentAgent(provider=provider)
    result = agent.run(
        NewAgentInput(
            name="lint_check",
            description="Checks for common lint issues in Python diffs",
            rules=[
                {
                    "rule_id": "lint:long-line",
                    "severity": "warning",
                    "trigger": "line > 120 chars",
                }
            ],
            input_fields=[
                {
                    "name": "diff",
                    "type": "str",
                    "required": True,
                    "description": "git diff",
                }
            ],
            trigger="pull_request",
        )
    )

    assert result.agent_source
    assert result.approved is True
