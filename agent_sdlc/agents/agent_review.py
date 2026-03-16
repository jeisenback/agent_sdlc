"""agent_sdlc/agents/agent_review.py

AgentReviewAgent (individual mode) — quality gate for a single agent
before it ships. Reviews source code, tests, runner, and pipeline entry.

No external network calls; primarily static analysis + optional
PromptReviewAgent delegation for prompt quality.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity

logger = logging.getLogger(__name__)

_SDK_PATTERNS = re.compile(
    r"Anthropic\s*\(|openai\.OpenAI\s*\(|anthropic\.Anthropic\s*\("
)
_KEY_PATTERNS = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*=\s*['\"][^'\"]{8,})",
    re.IGNORECASE,
)
_RETRY_CALL = re.compile(r"@with_retry|with_retry\(")
_EXTERNAL_CALL = re.compile(r"requests\.|httpx\.|urllib\.|subprocess\.run")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentReviewInput(BaseModel):
    agent_source: str
    test_source: str
    agent_name: str
    runner_source: Optional[str] = None
    pipeline_entry: Optional[str] = None


class AgentReviewResult(BaseModel):
    findings: List[Finding]
    approved: bool


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------


def _f(
    severity: FindingSeverity, rule: str, message: str, location: str = ""
) -> Finding:
    return Finding(
        severity=severity,
        rule=rule,
        message=message,
        location=location or "(agent source)",
    )


def _check_no_provider_protocol(source: str, agent_name: str) -> Optional[Finding]:
    if _SDK_PATTERNS.search(source):
        return _f(
            FindingSeverity.BLOCKER,
            "AgentReview:no-provider-protocol",
            f"Agent '{agent_name}' instantiates an LLM SDK directly; "
            "use ProviderProtocol instead.",
        )
    return None


def _check_no_finding_schema(source: str, agent_name: str) -> Optional[Finding]:
    uses_finding = (
        "from agent_sdlc.core.findings import" in source
        or "agent_sdlc.core.findings" in source
    )
    if not uses_finding:
        return _f(
            FindingSeverity.BLOCKER,
            "AgentReview:no-finding-schema",
            f"Agent '{agent_name}' does not import Finding/FindingSeverity "
            "from agent_sdlc.core.findings.",
        )
    return None


def _check_no_all_export(source: str, agent_name: str) -> Optional[Finding]:
    if "__all__" not in source:
        return _f(
            FindingSeverity.BLOCKER,
            "AgentReview:no-all-export",
            f"Agent '{agent_name}' module is missing an __all__ export list.",
        )
    return None


def _check_hardcoded_key(
    source: str, test_source: str, agent_name: str
) -> Optional[Finding]:
    combined = source + "\n" + test_source
    if _KEY_PATTERNS.search(combined):
        return _f(
            FindingSeverity.BLOCKER,
            "AgentReview:hardcoded-key",
            f"Possible hardcoded API key or secret found in '{agent_name}' "
            "source or tests.",
        )
    return None


def _check_untested_blockers(
    source: str, test_source: str, agent_name: str
) -> Optional[Finding]:
    """Check if BLOCKER-severity rules lack a test asserting approved=False."""
    # Find lines that define BLOCKER findings (look for BLOCKER severity references)
    blocker_rules = re.findall(
        r"FindingSeverity\.BLOCKER|['\"]blocker['\"]",
        source,
        re.IGNORECASE,
    )
    if not blocker_rules:
        return None  # No BLOCKER rules defined — nothing to check

    # Check if tests assert approved=False
    has_approved_false = bool(
        re.search(
            r"approved\s*[=!]=?\s*False|assert.*approved.*False|approved.*is.*False",
            test_source,
        )
    )
    if not has_approved_false:
        return _f(
            FindingSeverity.BLOCKER,
            "AgentReview:untested-blockers",
            f"Agent '{agent_name}' defines BLOCKER findings but no test asserts "
            "approved=False when a BLOCKER is present.",
            location="tests",
        )
    return None


def _check_no_retry(source: str, agent_name: str) -> Optional[Finding]:
    """Warn if external calls are made without @with_retry."""
    has_external = bool(_EXTERNAL_CALL.search(source))
    has_retry = bool(_RETRY_CALL.search(source))
    if has_external and not has_retry:
        return _f(
            FindingSeverity.WARNING,
            "AgentReview:no-retry",
            f"Agent '{agent_name}' makes external calls without @with_retry().",
        )
    return None


def _check_no_pipeline_entry(
    pipeline_entry: Optional[str], agent_name: str
) -> Optional[Finding]:
    if not pipeline_entry:
        return _f(
            FindingSeverity.WARNING,
            "AgentReview:no-pipeline-entry",
            f"Agent '{agent_name}' has no entry in .agent-pipeline.yml.",
            location=".agent-pipeline.yml",
        )
    return None


def _check_no_runner(
    runner_source: Optional[str], agent_name: str
) -> Optional[Finding]:
    if not runner_source:
        return _f(
            FindingSeverity.WARNING,
            "AgentReview:no-runner",
            f"Agent '{agent_name}' has no runner script for local invocation.",
            location="scripts/",
        )
    return None


def _check_prompt_quality(source: str, agent_name: str) -> List[Finding]:
    """Delegate to PromptReviewAgent for prompt quality check."""
    try:
        from agent_sdlc.agents.prompt_review import PromptReviewAgent, PromptReviewInput
        from agent_sdlc.core.providers import DummyLLMProvider
    except ImportError:
        logger.warning(
            "PromptReviewAgent not available — AgentReview:prompt-quality skipped"
        )
        return []

    # Extract the longest triple-quoted string as the prompt
    matches = re.findall(r'"""(.*?)"""', source, re.DOTALL)
    if not matches:
        return []
    prompt_text = max(matches, key=len).strip()
    if len(prompt_text) < 50:
        return []

    try:
        pr_agent = PromptReviewAgent(provider=DummyLLMProvider())
        pr_result = pr_agent.run(
            PromptReviewInput(
                prompt_text=prompt_text,
                source_location=f"agent_sdlc/agents/{agent_name}.py",
                agent_name=agent_name,
            )
        )
        # Surface WARNING-level and above findings from prompt review
        return [
            f.copy(
                update={
                    "rule": f"AgentReview:prompt-quality ({f.rule})",
                    "severity": FindingSeverity.WARNING,
                }
            )
            for f in pr_result.findings
            if f.severity in (FindingSeverity.BLOCKER, FindingSeverity.WARNING)
        ]
    except Exception as exc:
        logger.warning("PromptReviewAgent raised an error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# AgentReviewAgent
# ---------------------------------------------------------------------------


class AgentReviewAgent:
    """Reviews a single agent's source code, tests, runner, and pipeline entry."""

    def run(self, inp: AgentReviewInput) -> AgentReviewResult:
        findings: List[Finding] = []

        checks = [
            _check_no_provider_protocol(inp.agent_source, inp.agent_name),
            _check_no_finding_schema(inp.agent_source, inp.agent_name),
            _check_no_all_export(inp.agent_source, inp.agent_name),
            _check_hardcoded_key(inp.agent_source, inp.test_source, inp.agent_name),
            _check_untested_blockers(inp.agent_source, inp.test_source, inp.agent_name),
            _check_no_retry(inp.agent_source, inp.agent_name),
            _check_no_pipeline_entry(inp.pipeline_entry, inp.agent_name),
            _check_no_runner(inp.runner_source, inp.agent_name),
        ]
        findings = [f for f in checks if f is not None]
        findings += _check_prompt_quality(inp.agent_source, inp.agent_name)

        approved = all(f.severity != FindingSeverity.BLOCKER for f in findings)
        return AgentReviewResult(findings=findings, approved=approved)


__all__ = ["AgentReviewAgent", "AgentReviewInput", "AgentReviewResult"]
