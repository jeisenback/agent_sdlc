"""agent_sdlc/agents/agent_review.py

AgentReviewAgent — quality gate for individual agents and the full catalog.

mode=individual  Reviews a single agent's source, tests, runner, pipeline entry.
mode=system      Reviews the full agent catalog for portfolio-level issues:
                 rule overlaps, coverage gaps, naming inconsistencies, orphans.

No external network calls; primarily static analysis + optional
PromptReviewAgent delegation for prompt quality.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional

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


class SystemReviewInput(BaseModel):
    """Input for system-level catalog review."""

    agent_sources: Dict[str, str]  # agent_name → source
    pipeline_config: str  # .agent-pipeline.yml contents
    finding_namespaces: List[str]  # all Namespace: prefixes in use


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
# System-level rule helpers
# ---------------------------------------------------------------------------

_SDLC_STAGES = [
    "requirements",
    "design",
    "review",
    "testing",
    "deployment",
    "monitoring",
]

_GATE_NAMES = re.compile(r"\b(approved|passed|ready)\b")


def _sys_namespace_collision(
    agent_sources: Dict[str, str],
) -> List[Finding]:
    """BLOCKER: two agents use the same rule namespace prefix."""
    namespace_owners: Dict[str, List[str]] = defaultdict(list)
    for agent_name, source in agent_sources.items():
        for ns in re.findall(r"['\"]([A-Za-z][A-Za-z0-9_-]+):", source):
            namespace_owners[ns].append(agent_name)

    findings = []
    for ns, owners in namespace_owners.items():
        unique = list(dict.fromkeys(owners))  # deduplicate preserving order
        if len(unique) > 1:
            findings.append(
                _f(
                    FindingSeverity.BLOCKER,
                    "AgentReview:sys:namespace-collision",
                    f"Rule namespace '{ns}:' used by multiple agents: "
                    + ", ".join(f"'{a}'" for a in unique),
                    location="agent_sdlc/agents/",
                )
            )
    return findings


def _sys_orphan_agents(
    agent_sources: Dict[str, str], pipeline_config: str
) -> List[Finding]:
    """WARNING: agent exists but has no pipeline entry."""
    findings = []
    for agent_name in agent_sources:
        if agent_name not in pipeline_config:
            findings.append(
                _f(
                    FindingSeverity.WARNING,
                    "AgentReview:sys:orphan-agent",
                    f"Agent '{agent_name}' has no entry in .agent-pipeline.yml "
                    "and no CI trigger.",
                    location=f"agent_sdlc/agents/{agent_name}.py",
                )
            )
    return findings


def _sys_coverage_gap(agent_sources: Dict[str, str]) -> List[Finding]:
    """WARNING: an SDLC stage has no agent covering it."""
    combined = "\n".join(agent_sources.values()).lower()
    findings = []
    for stage in _SDLC_STAGES:
        if stage not in combined:
            findings.append(
                _f(
                    FindingSeverity.WARNING,
                    "AgentReview:sys:coverage-gap",
                    f"No agent appears to cover the '{stage}' SDLC stage.",
                    location="agent_sdlc/agents/",
                )
            )
    return findings


def _sys_inconsistent_gate(agent_sources: Dict[str, str]) -> List[Finding]:
    """WARNING: mixed use of approved/passed/ready across result models."""
    gate_names_used: set = set()
    for source in agent_sources.values():
        for m in _GATE_NAMES.finditer(source):
            gate_names_used.add(m.group(1))

    if len(gate_names_used) > 1:
        return [
            _f(
                FindingSeverity.WARNING,
                "AgentReview:sys:inconsistent-gate",
                "Inconsistent gate field names across agent result models: "
                + ", ".join(f"'{n}'" for n in sorted(gate_names_used)),
                location="agent_sdlc/agents/",
            )
        ]
    return []


def _sys_no_aggregation(
    agent_sources: Dict[str, str], pipeline_config: str
) -> List[Finding]:
    """WARNING: agents that post findings without routing through FindingAggregator."""
    if (
        "finding_aggregator" not in pipeline_config
        and "FindingAggregator" not in pipeline_config
    ):
        return [
            _f(
                FindingSeverity.WARNING,
                "AgentReview:sys:no-aggregation",
                "No FindingAggregator entry found in .agent-pipeline.yml; "
                "agents may post findings without unified aggregation.",
                location=".agent-pipeline.yml",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# AgentReviewAgent
# ---------------------------------------------------------------------------


class AgentReviewAgent:
    """Reviews individual agents or the full catalog (system mode)."""

    def run(self, inp: AgentReviewInput) -> AgentReviewResult:
        """Individual mode: review a single agent."""
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
        findings: List[Finding] = [f for f in checks if f is not None]
        findings += _check_prompt_quality(inp.agent_source, inp.agent_name)

        approved = all(f.severity != FindingSeverity.BLOCKER for f in findings)
        return AgentReviewResult(findings=findings, approved=approved)

    def run_system(self, inp: SystemReviewInput) -> AgentReviewResult:
        """System mode: review the full agent catalog for portfolio-level issues."""
        findings: List[Finding] = []
        findings += _sys_namespace_collision(inp.agent_sources)
        findings += _sys_orphan_agents(inp.agent_sources, inp.pipeline_config)
        findings += _sys_coverage_gap(inp.agent_sources)
        findings += _sys_inconsistent_gate(inp.agent_sources)
        findings += _sys_no_aggregation(inp.agent_sources, inp.pipeline_config)

        approved = all(f.severity != FindingSeverity.BLOCKER for f in findings)
        return AgentReviewResult(findings=findings, approved=approved)


__all__ = [
    "AgentReviewAgent",
    "AgentReviewInput",
    "AgentReviewResult",
    "SystemReviewInput",
]
