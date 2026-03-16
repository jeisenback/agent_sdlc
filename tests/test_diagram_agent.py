import pytest

from agent_sdlc.agents.diagram import (
    DiagramAgent,
    DiagramInput,
    DiagramResult,
    _strip_fences,
)
from agent_sdlc.core.providers import DummyLLMProvider

_SAMPLE_FLOWCHART = "flowchart TD\n    A[Start] --> B[Process] --> C[End]"
_SAMPLE_SEQUENCE = "sequenceDiagram\n    User->>Auth: login\n    Auth-->>User: token"


def _agent(response: str) -> DiagramAgent:
    return DiagramAgent(DummyLLMProvider(default=response))


def test_diagram_result_is_non_empty():
    agent = _agent(_SAMPLE_FLOWCHART)
    inp = DiagramInput(diagram_type="flowchart", description="Simple start-to-end flow")
    res = agent.run(inp)
    assert isinstance(res, DiagramResult)
    assert res.mermaid_syntax.strip() != ""


def test_diagram_result_has_no_fences():
    # Even if the LLM wraps output in fences, they must be stripped
    fenced = "```mermaid\n" + _SAMPLE_FLOWCHART + "\n```"
    agent = _agent(fenced)
    inp = DiagramInput(diagram_type="flowchart", description="flow")
    res = agent.run(inp)
    assert "```" not in res.mermaid_syntax


def test_diagram_result_has_no_fences_plain_fence():
    fenced = "```\n" + _SAMPLE_FLOWCHART + "\n```"
    agent = _agent(fenced)
    inp = DiagramInput(diagram_type="flowchart", description="flow")
    res = agent.run(inp)
    assert "```" not in res.mermaid_syntax


def test_diagram_sequence_type():
    agent = _agent(_SAMPLE_SEQUENCE)
    inp = DiagramInput(
        diagram_type="sequence",
        description="User logs in and gets a token",
        context="User, Auth service",
    )
    res = agent.run(inp)
    assert res.diagram_type == "sequence"
    assert res.mermaid_syntax.strip() != ""
    assert "```" not in res.mermaid_syntax


def test_diagram_title_defaults_to_type():
    agent = _agent(_SAMPLE_FLOWCHART)
    inp = DiagramInput(diagram_type="flowchart", description="flow")
    res = agent.run(inp)
    assert res.title == "flowchart"


def test_diagram_title_uses_provided_title():
    agent = _agent(_SAMPLE_FLOWCHART)
    inp = DiagramInput(
        diagram_type="flowchart", description="flow", title="Agent Pipeline"
    )
    res = agent.run(inp)
    assert res.title == "Agent Pipeline"


def test_diagram_agent_flow_type():
    agent = _agent("flowchart TD\n    PO --> PG --> DoR")
    inp = DiagramInput(
        diagram_type="agentFlow",
        description="PO agent then process gap then DoR",
    )
    res = agent.run(inp)
    assert res.diagram_type == "agentFlow"
    assert "```" not in res.mermaid_syntax


def test_diagram_er_type():
    er = "erDiagram\n    USER ||--o{ ORDER : places"
    agent = _agent(er)
    inp = DiagramInput(
        diagram_type="erDiagram",
        description="User places many orders",
    )
    res = agent.run(inp)
    assert res.diagram_type == "erDiagram"
    assert "```" not in res.mermaid_syntax


def test_strip_fences_no_fences():
    raw = "flowchart TD\n    A --> B"
    assert _strip_fences(raw) == raw


def test_strip_fences_mermaid_fence():
    raw = "```mermaid\nflowchart TD\n    A --> B\n```"
    assert _strip_fences(raw) == "flowchart TD\n    A --> B"


def test_strip_fences_plain_fence():
    raw = "```\nflowchart TD\n    A --> B\n```"
    assert _strip_fences(raw) == "flowchart TD\n    A --> B"


@pytest.mark.parametrize(
    "diagram_type",
    ["sequence", "flowchart", "classDiagram", "erDiagram", "agentFlow"],
)
def test_all_diagram_types_accepted(diagram_type: str) -> None:
    agent = _agent("flowchart TD\n    A --> B")
    inp = DiagramInput(diagram_type=diagram_type, description="test")  # type: ignore[arg-type]
    res = agent.run(inp)
    assert res.diagram_type == diagram_type
