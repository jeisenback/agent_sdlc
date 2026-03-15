from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class ProductOwnerInput(BaseModel):
    title: str
    description: str
    product_goals: Optional[str] = None
    target_users: Optional[str] = None
    existing_features: Optional[str] = None


class ProductOwnerResult(BaseModel):
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


class ProductOwnerAgent:
    """Backlog-grooming strategic review agent.

    Runs before DoR — asks "should we build this?" not "is the ticket
    formatted correctly?". Distinct from IssueRefinementAgent (procedural DoR)
    and ProcessGapAgent (business context gaps).

    Run order convention:
        ProductOwnerAgent → ProcessGapAgent → IssueRefinementAgent

    Rules namespace: PO:
    Returns a ProductOwnerResult; approved=False if any BLOCKER present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: ProductOwnerInput) -> ProductOwnerResult:
        goals_ctx = (
            f"\nProduct goals / OKRs:\n{inp.product_goals}" if inp.product_goals else ""
        )
        users_ctx = f"\nTarget users:\n{inp.target_users}" if inp.target_users else ""
        features_ctx = (
            f"\nExisting features (for overlap detection):\n{inp.existing_features}"
            if inp.existing_features
            else ""
        )
        prompt = (
            "You are a Product Owner conducting a backlog-grooming strategic review.\n"
            "Your job is to decide whether this issue should be built at all and whether\n"
            "it is strategically sound — not whether the ticket is formatted correctly.\n\n"
            f"Issue title: '{inp.title}'\n"
            f"Issue description:\n{inp.description}"
            f"{goals_ctx}{users_ctx}{features_ctx}\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            '{"location":"title|description|goals|users","severity":"blocker|warning|suggestion",'
            '"rule":"PO:<rule-id>","message":"<what is wrong>","suggestion":"<how to fix>"}\n'
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "Strategic review rules (namespace PO:):\n"
            "  PO:value-unclear          — No stated user benefit or business outcome: the issue does\n"
            "                              not explain what value it delivers to any user or the business\n"
            "                              (BLOCKER)\n"
            "  PO:no-target-user         — No identified user persona or segment: impossible to assess\n"
            "                              value without knowing who benefits (BLOCKER)\n"
            "  PO:unmeasurable-success   — No success metric, KPI, or measurable outcome: no way to\n"
            "                              know if this feature succeeded after delivery (BLOCKER)\n"
            "  PO:scope-creep            — Addresses more than one distinct user problem: should be\n"
            "                              split into separate backlog items (WARNING)\n"
            "  PO:overlap                — Described functionality duplicates or significantly overlaps\n"
            "                              an existing feature listed above (WARNING)\n"
            "  PO:assumption-unstated    — Assumes user behaviour or need that is not validated, cited,\n"
            "                              or referenced (WARNING)\n"
            "  PO:effort-value-imbalance — Estimated effort appears disproportionate to the stated\n"
            "                              value; high complexity for unclear or marginal benefit (WARNING)\n"
            "  PO:ux-neglected           — No mention of user-facing interaction or UX considerations;\n"
            "                              issue reads as purely backend with no user impact considered\n"
            "                              (SUGGESTION)\n"
            "  PO:title-jargon           — Title uses internal technical jargon not meaningful to end\n"
            "                              users or non-technical stakeholders (SUGGESTION)\n\n"
            "Return [] if the issue passes all strategic review criteria."
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return ProductOwnerResult(findings=findings)


__all__ = ["ProductOwnerAgent", "ProductOwnerInput", "ProductOwnerResult"]
