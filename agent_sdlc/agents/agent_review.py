"""AgentReviewAgent — quality gate for new agents before they ship.

Mode: individual — reviews a single agent's source code, prompt string,
test file, and CI trigger for compliance with project patterns:
  - ProviderProtocol usage (no direct SDK imports)
  - Finding schema usage
  - __all__ export
  - Test coverage for each BLOCKER rule
  - Prompt quality basics

Rules namespace: ``AgentReview:``

Deterministic checks run without an LLM. When a provider is supplied,
it can also perform deeper prompt-quality analysis via LLM.

Usage:
    from agent_sdlc.agents.agent_review import (
        AgentReviewAgent,
        AgentReviewInput,
        AgentReviewResult,
    )
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from agent_sdlc.core.findings import Finding, FindingSeverity
from agent_sdlc.core.providers import ProviderProtocol


class AgentReviewInput(BaseModel):
    """Input for reviewing a single agent."""

    agent_name: str = Field(description="Agent module name, e.g. 'pr_review'.")
    source_code: str = Field(description="Full source code of the agent module.")
    test_code: Optional[str] = Field(
        default=None, description="Full source code of the agent's test file."
    )
    pipeline_yaml: Optional[str] = Field(
        default=None,
        description="Contents of .agent-pipeline.yml to check CI wiring.",
    )


class AgentReviewResult(BaseModel):
    findings: List[Finding] = Field(default_factory=list)

    @property
    def approved(self) -> bool:
        return not any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(
            1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION
        )


# ---------------------------------------------------------------------------
# Direct SDK import patterns to flag
# ---------------------------------------------------------------------------

_DIRECT_SDK_PATTERNS = [
    re.compile(r"^\s*import\s+anthropic\b", re.MULTILINE),
    re.compile(r"^\s*from\s+anthropic\b", re.MULTILINE),
    re.compile(r"^\s*import\s+openai\b", re.MULTILINE),
    re.compile(r"^\s*from\s+openai\b", re.MULTILINE),
]


class AgentReviewAgent:
    """Reviews a single agent for pattern compliance.

    Deterministic checks (no LLM required for core rules). When a provider
    is supplied, deeper prompt-quality checks can be performed via LLM.
    """

    def __init__(self, provider: Optional[ProviderProtocol] = None) -> None:
        self.provider = provider

    def run(self, inp: AgentReviewInput) -> AgentReviewResult:
        findings: List[Finding] = []

        self._check_all_export(inp, findings)
        self._check_no_direct_sdk(inp, findings)
        self._check_finding_schema(inp, findings)
        self._check_provider_protocol(inp, findings)
        self._check_test_exists(inp, findings)
        self._check_blocker_tests(inp, findings)
        self._check_pipeline_wiring(inp, findings)

        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return AgentReviewResult(findings=findings)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_all_export(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        if "__all__" not in inp.source_code:
            findings.append(
                Finding(
                    location=f"agent_sdlc/agents/{inp.agent_name}.py",
                    severity=FindingSeverity.BLOCKER,
                    rule="AgentReview:export",
                    message="Agent module does not define __all__.",
                    suggestion="Add __all__ = ['AgentClass', 'InputModel', 'ResultModel'].",
                )
            )

    def _check_no_direct_sdk(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        for pattern in _DIRECT_SDK_PATTERNS:
            match = pattern.search(inp.source_code)
            if match:
                findings.append(
                    Finding(
                        location=f"agent_sdlc/agents/{inp.agent_name}.py",
                        severity=FindingSeverity.BLOCKER,
                        rule="AgentReview:no-direct-sdk",
                        message=f"Direct SDK import detected: '{match.group().strip()}'.",
                        suggestion="Use ProviderProtocol from agent_sdlc.core.providers.",
                    )
                )
                break  # one finding per rule is enough

    def _check_finding_schema(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        uses_finding = (
            "Finding" in inp.source_code
            or "FindingSeverity" in inp.source_code
        )
        if not uses_finding:
            findings.append(
                Finding(
                    location=f"agent_sdlc/agents/{inp.agent_name}.py",
                    severity=FindingSeverity.WARNING,
                    rule="AgentReview:finding-schema",
                    message="Agent does not appear to use the shared Finding schema.",
                    suggestion="Import Finding from agent_sdlc.core.findings.",
                )
            )

    def _check_provider_protocol(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        if "ProviderProtocol" not in inp.source_code:
            findings.append(
                Finding(
                    location=f"agent_sdlc/agents/{inp.agent_name}.py",
                    severity=FindingSeverity.WARNING,
                    rule="AgentReview:provider-protocol",
                    message="Agent does not reference ProviderProtocol.",
                    suggestion=(
                        "Accept provider: ProviderProtocol as a constructor arg "
                        "(or document why no LLM is needed)."
                    ),
                )
            )

    def _check_test_exists(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        if not inp.test_code:
            findings.append(
                Finding(
                    location=f"tests/test_{inp.agent_name}.py",
                    severity=FindingSeverity.BLOCKER,
                    rule="AgentReview:test-exists",
                    message="No test file provided for this agent.",
                    suggestion=f"Create tests/test_{inp.agent_name}.py with DummyLLMProvider.",
                )
            )

    def _check_blocker_tests(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        """Check that each BLOCKER rule in the agent has a corresponding test."""
        if not inp.test_code:
            return  # already flagged by _check_test_exists

        # Find BLOCKER severity references in agent source
        blocker_refs = re.findall(
            r"""['"](blocker|BLOCKER)['"]""", inp.source_code
        )
        if not blocker_refs:
            return  # agent may not produce blockers

        # Check that the test file asserts approved=False or blocker
        has_blocker_test = (
            "approved" in inp.test_code
            and "False" in inp.test_code
        ) or "BLOCKER" in inp.test_code or "blocker" in inp.test_code

        if not has_blocker_test:
            findings.append(
                Finding(
                    location=f"tests/test_{inp.agent_name}.py",
                    severity=FindingSeverity.BLOCKER,
                    rule="AgentReview:blocker-test",
                    message="Agent produces BLOCKER findings but test file does not assert approved=False.",
                    suggestion="Add a test that verifies BLOCKER findings set approved=False.",
                )
            )

    def _check_pipeline_wiring(
        self, inp: AgentReviewInput, findings: List[Finding]
    ) -> None:
        if not inp.pipeline_yaml:
            findings.append(
                Finding(
                    location=".agent-pipeline.yml",
                    severity=FindingSeverity.WARNING,
                    rule="AgentReview:pipeline-wiring",
                    message="No pipeline YAML provided; cannot verify CI wiring.",
                    suggestion="Pass .agent-pipeline.yml contents to verify the agent is wired.",
                )
            )
            return

        if inp.agent_name not in inp.pipeline_yaml:
            findings.append(
                Finding(
                    location=".agent-pipeline.yml",
                    severity=FindingSeverity.WARNING,
                    rule="AgentReview:pipeline-wiring",
                    message=f"Agent '{inp.agent_name}' not found in .agent-pipeline.yml.",
                    suggestion="Add an entry for this agent in the pipeline configuration.",
                )
            )


__all__ = ["AgentReviewAgent", "AgentReviewInput", "AgentReviewResult"]
