from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol

ArtifactType = Literal["html", "jsx", "css", "design_spec", "other"]


class UIDesignInput(BaseModel):
    artifact: str
    artifact_type: ArtifactType
    component_name: Optional[str] = None
    design_system: Optional[str] = None


class UIDesignResult(BaseModel):
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


class UIDesignAgent:
    """Visual consistency and accessibility review agent.

    Reviews HTML/JSX/CSS source or design spec prose for WCAG accessibility
    violations, hardcoded values outside design tokens, and visual consistency
    issues.

    Rules namespace: UI:
    Returns a UIDesignResult; approved=False if any BLOCKER findings present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: UIDesignInput) -> UIDesignResult:
        component_ctx = (
            f"\nComponent name: {inp.component_name}" if inp.component_name else ""
        )
        design_ctx = (
            f"\nDesign system: {inp.design_system}" if inp.design_system else ""
        )
        font_rule = (
            "  UI:font-outside-scale   — Font size is not on the type scale defined by the\n"
            f"                            {inp.design_system} design system (WARNING)\n"
            if inp.design_system
            else ""
        )
        prompt = (
            "You are a UI design and accessibility reviewer.\n"
            f"Review the following {inp.artifact_type} artifact for accessibility and visual consistency."
            f"{component_ctx}{design_ctx}\n\n"
            f"--- ARTIFACT START ---\n{inp.artifact}\n--- ARTIFACT END ---\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            '{"location":"<element, selector, or line>","severity":"blocker|warning|suggestion",'
            '"rule":"UI:<rule-id>","message":"<what is wrong>","suggestion":"<how to fix>"}\n'
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "UI rules to check (namespace UI:):\n"
            "  UI:missing-alt-text     — An <img> element (or img role) has no alt attribute, or\n"
            "                            has an empty alt only on a non-decorative image. Screen\n"
            "                            readers will read the filename instead. (BLOCKER)\n"
            "  UI:color-contrast       — A detectable foreground/background color pair fails the\n"
            "                            WCAG AA minimum contrast ratio (4.5:1 for normal text,\n"
            "                            3:1 for large text). (BLOCKER)\n"
            "  UI:hardcoded-color      — A literal hex (#rrggbb), rgb(), or hsl() value is used\n"
            "                            directly instead of a CSS variable or design token.\n"
            "                            (WARNING)\n"
            "  UI:hardcoded-spacing    — A pixel or rem margin/padding value is used that does not\n"
            "                            correspond to the spacing scale (4/8/12/16/24/32/48px).\n"
            "                            (WARNING)\n"
            "  UI:responsive-missing   — A fixed pixel width is set on a container with no\n"
            "                            accompanying breakpoint override or max-width. (WARNING)\n"
            "  UI:component-inline     — A UI pattern (button, input, card) is implemented inline\n"
            "                            with raw HTML/CSS rather than using a component library\n"
            "                            element. (WARNING)\n"
            f"{font_rule}"
            "  UI:inconsistent-radius  — A border-radius value differs from sibling or related\n"
            "                            components without a stated reason. (SUGGESTION)\n"
            "  UI:z-index-magic        — An arbitrary z-index value is used without a comment\n"
            "                            explaining the stacking context. (SUGGESTION)\n\n"
            "Return [] if the artifact passes all UI checks."
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return UIDesignResult(findings=findings)


__all__ = ["UIDesignAgent", "UIDesignInput", "UIDesignResult", "ArtifactType"]
