"""Unit tests for AgentReviewAgent (individual mode).

All BLOCKER rules are tested with DummyLLMProvider — zero network calls.
"""

from __future__ import annotations

from agent_sdlc.agents.agent_review import AgentReviewAgent, AgentReviewInput
from agent_sdlc.core.findings import FindingSeverity

# ---------------------------------------------------------------------------
# Minimal valid agent source — passes all checks
# ---------------------------------------------------------------------------

_VALID_SOURCE = '''\
"""A sample agent."""
from __future__ import annotations
from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol
from pydantic import BaseModel

class MyInput(BaseModel):
    text: str

class MyResult(BaseModel):
    findings: list
    approved: bool

class MyAgent:
    def __init__(self, provider: ProviderProtocol):
        self.provider = provider

    def run(self, inp: MyInput) -> MyResult:
        findings = []
        if not inp.text:
            findings.append(Finding(
                severity=FindingSeverity.BLOCKER,
                rule="my:rule",
                message="Text is empty.",
            ))
        approved = all(f.severity != FindingSeverity.BLOCKER for f in findings)
        return MyResult(findings=findings, approved=approved)

__all__ = ["MyAgent", "MyInput", "MyResult"]
'''

_VALID_TEST = """\
from agent_sdlc.agents.my_agent import MyAgent, MyInput

def test_blocker_when_empty():
    result = MyAgent(provider=None).run(MyInput(text=""))
    assert result.approved is False

def test_passes_with_text():
    result = MyAgent(provider=None).run(MyInput(text="hello"))
    assert result.approved is True
"""


def _run(agent_source=_VALID_SOURCE, test_source=_VALID_TEST, **kwargs):
    inp = AgentReviewInput(
        agent_source=agent_source,
        test_source=test_source,
        agent_name="my_agent",
        **kwargs,
    )
    return AgentReviewAgent().run(inp)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_agent_passes_all_blocker_checks():
    result = _run(
        runner_source="# runner",
        pipeline_entry="agent: my_agent",
    )
    blocker_rules = [
        f.rule for f in result.findings if f.severity == FindingSeverity.BLOCKER
    ]
    assert blocker_rules == [], f"Unexpected BLOCKERs: {blocker_rules}"
    assert result.approved is True


# ---------------------------------------------------------------------------
# BLOCKER: no-provider-protocol
# ---------------------------------------------------------------------------


def test_no_provider_protocol_when_sdk_instantiated_directly():
    bad_source = _VALID_SOURCE.replace(
        "from agent_sdlc.core.providers import ProviderProtocol",
        "import anthropic\nclient = anthropic.Anthropic(api_key='x')",
    )
    result = _run(agent_source=bad_source)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:no-provider-protocol" in rules
    assert result.approved is False


# ---------------------------------------------------------------------------
# BLOCKER: no-finding-schema
# ---------------------------------------------------------------------------


def test_no_finding_schema_when_import_missing():
    bad_source = _VALID_SOURCE.replace(
        "from agent_sdlc.core.findings import Finding, FindingSeverity\n",
        "",
    )
    result = _run(agent_source=bad_source)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:no-finding-schema" in rules
    assert result.approved is False


# ---------------------------------------------------------------------------
# BLOCKER: no-all-export
# ---------------------------------------------------------------------------


def test_no_all_export_when_dunder_all_missing():
    bad_source = _VALID_SOURCE.replace(
        '__all__ = ["MyAgent", "MyInput", "MyResult"]', ""
    )
    result = _run(agent_source=bad_source)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:no-all-export" in rules
    assert result.approved is False


# ---------------------------------------------------------------------------
# BLOCKER: hardcoded-key
# ---------------------------------------------------------------------------


def test_hardcoded_key_detected_in_source():
    bad_source = _VALID_SOURCE + '\nAPI_KEY = "sk-abcdefghijklmnopqrstuvwxyz1234"\n'
    result = _run(agent_source=bad_source)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:hardcoded-key" in rules
    assert result.approved is False


def test_hardcoded_key_detected_in_tests():
    bad_test = _VALID_TEST + '\nSECRET = "sk-abcdefghijklmnopqrstuvwxyz1234"\n'
    result = _run(test_source=bad_test)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:hardcoded-key" in rules
    assert result.approved is False


# ---------------------------------------------------------------------------
# BLOCKER: untested-blockers
# ---------------------------------------------------------------------------


def test_untested_blockers_when_no_approved_false_assertion():
    test_without_approved_check = """\
from agent_sdlc.agents.my_agent import MyAgent, MyInput

def test_something():
    result = MyAgent(provider=None).run(MyInput(text=""))
    assert len(result.findings) > 0
"""
    result = _run(test_source=test_without_approved_check)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:untested-blockers" in rules
    assert result.approved is False


# ---------------------------------------------------------------------------
# WARNING: no-pipeline-entry
# ---------------------------------------------------------------------------


def test_no_pipeline_entry_warning_when_absent():
    result = _run(pipeline_entry=None, runner_source="# runner")
    rules = [f.rule for f in result.findings]
    assert "AgentReview:no-pipeline-entry" in rules
    # WARNING only — should not affect approved when no BLOCKERs
    assert result.approved is True


# ---------------------------------------------------------------------------
# WARNING: no-runner
# ---------------------------------------------------------------------------


def test_no_runner_warning_when_absent():
    result = _run(pipeline_entry="agent: my_agent", runner_source=None)
    rules = [f.rule for f in result.findings]
    assert "AgentReview:no-runner" in rules
    assert result.approved is True
