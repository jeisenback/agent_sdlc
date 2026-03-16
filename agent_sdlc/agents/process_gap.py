from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class ProcessGapInput(BaseModel):
    """Input for issue-level business context check (mode='issue')."""

    title: str
    description: str
    mode: Literal["issue"] = "issue"


class WorkflowGapInput(BaseModel):
    """Input for workflow-level dev process gap analysis (mode='workflow').

    Analyses repo-wide process artifacts — CLAUDE.md, CI workflows, CODEOWNERS,
    TASKS.md, and recent PR/issue stats — for structural dev and business process
    gaps. Intended to run weekly via scheduled CI.
    """

    mode: Literal["workflow"] = "workflow"
    claude_md: str
    ci_workflows: List[str]
    codeowners: Optional[str] = None
    tasks_md: Optional[str] = None
    recent_pr_stats: Optional[str] = None
    issue_stats: Optional[str] = None


class ProcessGapResult(BaseModel):
    findings: List[Finding]

    @property
    def approved(self) -> bool:
        """True only when there are zero BLOCKER findings."""
        return not any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.SUGGESTION)


_FINDING_SCHEMA = (
    '{"location":"<artifact or section>","severity":"blocker|warning|suggestion",'
    '"rule":"<namespace>:<rule-id>","message":"<what is missing>","suggestion":"<how to fix>"}'
)

_SORT_ORDER = {
    FindingSeverity.BLOCKER: 0,
    FindingSeverity.WARNING: 1,
    FindingSeverity.SUGGESTION: 2,
}


class ProcessGapAgent:
    """Process gap agent supporting issue-level and workflow-level modes.

    mode='issue':
        Checks whether an issue has sufficient business context — the "why",
        measurable outcomes, target user, and rollback plan. Complements
        IssueRefinementAgent (procedural DoR) by asking whether the issue
        *should* be built and whether the business context is complete.
        Rules namespace: biz:

    mode='workflow':
        Analyses repo-wide process artifacts for structural dev and business
        process gaps: no DoD, no deploy smoke, no incident runbook, no feature
        flags strategy, etc. Intended to run weekly via scheduled CI and post
        a gap report to a pinned GitHub issue.
        Rules namespaces: dev: and biz:

    Returns a ProcessGapResult; approved=False if any BLOCKER findings present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: Union[ProcessGapInput, WorkflowGapInput]) -> ProcessGapResult:
        if inp.mode == "issue":
            assert isinstance(inp, ProcessGapInput)
            prompt = self._issue_prompt(inp)
        else:
            assert isinstance(inp, WorkflowGapInput)
            prompt = self._workflow_prompt(inp)
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        findings.sort(key=lambda f: _SORT_ORDER[f.severity])
        return ProcessGapResult(findings=findings)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _issue_prompt(self, inp: ProcessGapInput) -> str:
        return (
            "You are a business process reviewer for software issues.\n"
            "Check whether this issue has sufficient business context to proceed.\n\n"
            f"Issue title: '{inp.title}'\n"
            f"Issue description:\n{inp.description}\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            f"{_FINDING_SCHEMA}\n"
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "Business process rules to check (namespace biz:):\n"
            "  biz:no-why              — No stated business value: the issue explains what to build but\n"
            "                            not why it matters or what problem it solves (BLOCKER)\n"
            "  biz:no-success-metric   — No measurable outcome: no KPI, metric, or verifiable result\n"
            "                            defined so the team can tell when this is done (BLOCKER)\n"
            "  biz:no-target-user      — No identified user: no persona, segment, or role that benefits\n"
            "                            from this change is mentioned (BLOCKER)\n"
            "  biz:scope-creep-risk    — The issue appears to address multiple unrelated concerns or\n"
            "                            bundle features that should be separate issues (WARNING)\n"
            "  biz:no-stakeholder      — No product owner or decision-maker is identified as responsible\n"
            "                            for this work (WARNING)\n"
            "  biz:no-rollback-plan    — No mention of what happens if the change needs to be reverted\n"
            "                            or rolled back in production (SUGGESTION)\n"
            "  biz:no-uat-gate         — No acceptance step before production is defined: no mention\n"
            "                            of UAT, canary, or staged rollout (SUGGESTION)\n\n"
            "Return [] if all business process criteria are met."
        )

    def _workflow_prompt(self, inp: WorkflowGapInput) -> str:
        workflows_text = (
            "\n---\n".join(inp.ci_workflows) if inp.ci_workflows else "(none)"
        )
        codeowners_text = inp.codeowners or "(not present)"
        tasks_text = inp.tasks_md or "(not present)"
        pr_stats_text = inp.recent_pr_stats or "(not provided)"
        issue_stats_text = inp.issue_stats or "(not provided)"

        return (
            "You are a dev process analyst reviewing a software repository for\n"
            "structural development and business process gaps.\n\n"
            "=== CLAUDE.md ===\n"
            f"{inp.claude_md}\n\n"
            "=== CI Workflows ===\n"
            f"{workflows_text}\n\n"
            "=== CODEOWNERS ===\n"
            f"{codeowners_text}\n\n"
            "=== TASKS.md ===\n"
            f"{tasks_text}\n\n"
            "=== Recent PR stats (gh pr list JSON) ===\n"
            f"{pr_stats_text}\n\n"
            "=== Recent issue stats (gh issue list JSON) ===\n"
            f"{issue_stats_text}\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            f"{_FINDING_SCHEMA}\n"
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "Dev workflow rules (namespace dev:):\n"
            "  dev:no-dod               — No Definition of Done defined anywhere in the repo (BLOCKER)\n"
            "  dev:no-deploy-smoke      — No post-deploy verification or smoke test step in CI (BLOCKER)\n"
            "  dev:no-incident-runbook  — No documented incident response or on-call runbook (WARNING)\n"
            "  dev:no-feature-flags     — No feature flag strategy for risky rollouts mentioned (WARNING)\n"
            "  dev:no-changelog         — No CHANGELOG or release communication process defined (WARNING)\n"
            "  dev:no-rollback-procedure— No documented rollback or hotfix path (WARNING)\n"
            "  dev:weak-review-policy   — PR approval policy not documented or enforced in CI (WARNING)\n"
            "  dev:single-reviewer      — Only one person can approve PRs — bus-factor risk (SUGGESTION)\n"
            "  dev:no-escalation-path   — No documented escalation for blocked or stale issues (SUGGESTION)\n\n"
            "Business process rules (namespace biz:):\n"
            "  biz:no-uat-gate          — No UAT or stakeholder sign-off gate before prod (WARNING)\n"
            "  biz:no-feedback-loop     — No post-release user feedback mechanism defined (WARNING)\n"
            "  biz:no-traceability      — Issues not traceable to a requirements or design doc (WARNING)\n"
            "  biz:no-release-comms     — No release communication plan documented (SUGGESTION)\n"
            "  biz:no-product-owner     — No product owner identified in CODEOWNERS or docs (SUGGESTION)\n\n"
            "Return [] if no gaps are found."
        )


__all__ = [
    "ProcessGapAgent",
    "ProcessGapInput",
    "WorkflowGapInput",
    "ProcessGapResult",
]
