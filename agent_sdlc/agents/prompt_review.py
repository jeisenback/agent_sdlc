from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from agent_sdlc.core.findings import Finding, FindingSeverity, parse_findings_from_json
from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol


class PromptReviewInput(BaseModel):
    prompt_text: str
    source_location: Optional[str] = None
    expected_output_format: Optional[
        Literal["json", "markdown", "plain", "structured"]
    ] = None
    agent_name: Optional[str] = None


class PromptReviewResult(BaseModel):
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


class PromptReviewAgent:
    """LLM prompt quality gate agent.

    Reviews an LLM prompt string for prompt engineering best practices:
    format specification, injection safety, fallback instructions, role framing,
    clarity, output schema completeness, and token efficiency.

    Rules namespace: Prompt:
    Returns a PromptReviewResult; approved=False if any BLOCKER findings present.
    Testable offline via DummyLLMProvider with pre-canned JSON responses.
    """

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: PromptReviewInput) -> PromptReviewResult:
        location = inp.source_location or "(prompt)"
        agent_ctx = f" (agent: {inp.agent_name})" if inp.agent_name else ""
        format_ctx = (
            f" The prompt is expected to produce {inp.expected_output_format} output."
            if inp.expected_output_format
            else ""
        )
        prompt = (
            f"You are a prompt engineering reviewer.{agent_ctx}\n"
            f"Review the following LLM prompt for quality and safety issues.{format_ctx}\n\n"
            f"--- PROMPT START ---\n{inp.prompt_text}\n--- PROMPT END ---\n\n"
            "Return ONLY a raw JSON array — no markdown fences, no prose. Each element:\n"
            '{"location":"<file:line or prompt section>","severity":"blocker|warning|suggestion",'
            '"rule":"Prompt:<rule-id>","message":"<what is wrong>","suggestion":"<how to fix>"}\n'
            'IMPORTANT: all string values must be valid JSON — escape any double-quotes inside strings as \\".\n\n'
            "Rules to check (namespace Prompt:):\n"
            "  Prompt:format-unspecified      — Expects structured output (JSON/list) but contains no\n"
            "                                   explicit format instruction (BLOCKER)\n"
            "  Prompt:injection-vector        — User-supplied input is interpolated directly with no\n"
            "                                   isolation boundary, delimiter, or sanitisation instruction\n"
            "                                   that prevents the user from injecting instructions (BLOCKER)\n"
            "  Prompt:missing-fallback        — The prompt says to return a list/array but gives no\n"
            "                                   instruction for what to return when there are no findings\n"
            "                                   (e.g. 'Return [] if nothing found') (WARNING)\n"
            "  Prompt:no-role                 — No system persona or role framing is present\n"
            "                                   (e.g. 'You are a ...') (WARNING)\n"
            "  Prompt:ambiguous-instruction   — Contains vague imperatives ('check this', 'review it')\n"
            "                                   with no specified criteria or rubric (WARNING)\n"
            "  Prompt:output-schema-incomplete— JSON output is requested but not all required fields\n"
            "                                   are specified in the prompt (WARNING)\n"
            "  Prompt:example-missing         — The prompt is complex (>200 chars) but contains no\n"
            "                                   few-shot example to guide the model (SUGGESTION)\n"
            "  Prompt:negation-heavy          — The instructions are primarily negative ('do not', 'never')\n"
            "                                   rather than positively framed (SUGGESTION)\n"
            "  Prompt:token-waste             — The same constraint or instruction is duplicated or\n"
            "                                   restated more than twice (SUGGESTION)\n\n"
            f"The prompt is from: {location}\n"
            "Return [] if the prompt passes all quality checks."
        )
        text = self.llm.ask_text(prompt)
        findings = parse_findings_from_json(text)
        _order = {
            FindingSeverity.BLOCKER: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.SUGGESTION: 2,
        }
        findings.sort(key=lambda f: _order[f.severity])
        return PromptReviewResult(findings=findings)


__all__ = ["PromptReviewAgent", "PromptReviewInput", "PromptReviewResult"]
