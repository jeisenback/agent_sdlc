from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from agent_sdlc.core.llm_wrapper import LLMWrapper
from agent_sdlc.core.providers import ProviderProtocol

DiagramType = Literal["sequence", "flowchart", "classDiagram", "erDiagram", "agentFlow"]


class DiagramInput(BaseModel):
    diagram_type: DiagramType
    description: str
    context: Optional[str] = None
    title: Optional[str] = None


class DiagramResult(BaseModel):
    mermaid_syntax: str
    title: str
    diagram_type: str


class DiagramAgent:
    """Mermaid diagram generation agent.

    Accepts a structured description and returns valid Mermaid syntax that
    can be embedded directly in GitHub PR/issue comments as ```mermaid blocks.

    Supported diagram types: sequence, flowchart, classDiagram, erDiagram,
    agentFlow (treated as flowchart for Mermaid compatibility).

    Output is raw Mermaid syntax only — no fences, no prose.
    Testable offline via DummyLLMProvider with pre-canned syntax responses.
    """

    # Map diagram_type to the Mermaid keyword used at the top of the diagram
    _MERMAID_KEYWORD: dict[str, str] = {
        "sequence": "sequenceDiagram",
        "flowchart": "flowchart TD",
        "classDiagram": "classDiagram",
        "erDiagram": "erDiagram",
        "agentFlow": "flowchart TD",
    }

    def __init__(self, provider: ProviderProtocol) -> None:
        self.llm = LLMWrapper(provider)

    def run(self, inp: DiagramInput) -> DiagramResult:
        keyword = self._MERMAID_KEYWORD[inp.diagram_type]
        title = inp.title or inp.diagram_type
        context_section = (
            f"\nContext (use these names/identifiers):\n{inp.context}"
            if inp.context
            else ""
        )
        prompt = (
            f"You are a Mermaid diagram generator.\n"
            f"Generate a {inp.diagram_type} diagram for the following description.\n\n"
            f"Description:\n{inp.description}"
            f"{context_section}\n\n"
            f"Rules:\n"
            f"  - Start the diagram with: {keyword}\n"
            f"  - Return ONLY the raw Mermaid syntax — no markdown fences (no ```), no prose,\n"
            f"    no explanations before or after the diagram.\n"
            f"  - Use only valid Mermaid {inp.diagram_type} syntax.\n"
            f"  - Keep the diagram concise and readable.\n"
            f"  - If a title is needed, use the Mermaid '---\\ntitle: {title}\\n---' frontmatter\n"
            f"    block before the diagram keyword.\n"
        )
        raw = self.llm.ask_text(prompt)
        mermaid_syntax = _strip_fences(raw).strip()
        return DiagramResult(
            mermaid_syntax=mermaid_syntax,
            title=title,
            diagram_type=inp.diagram_type,
        )


def _strip_fences(text: str) -> str:
    """Remove markdown code fences (```mermaid ... ``` or ``` ... ```)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence line
        inner = lines[1:] if lines[0].startswith("```") else lines
        # Drop closing fence line
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        return "\n".join(inner)
    return stripped


__all__ = ["DiagramAgent", "DiagramInput", "DiagramResult", "DiagramType"]
