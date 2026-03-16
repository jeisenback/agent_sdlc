from agent_sdlc.agents.prompt_review import PromptReviewAgent, PromptReviewInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider


def _agent(response: str = "[]") -> PromptReviewAgent:
    return PromptReviewAgent(DummyLLMProvider(default=response))


def test_prompt_review_approved_when_no_findings():
    agent = _agent("[]")
    inp = PromptReviewInput(
        prompt_text=(
            "You are a code reviewer.\n"
            "Review the diff and return a raw JSON array of findings. "
            '{"location":"...","severity":"blocker|warning|suggestion","rule":"...","message":"..."}.\n'
            "Return [] if no findings."
        ),
        expected_output_format="json",
    )
    res = agent.run(inp)
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


def test_prompt_review_blocker_format_unspecified():
    sample = (
        '[{"location":"prompt","severity":"blocker","rule":"Prompt:format-unspecified",'
        '"message":"No format instruction","suggestion":"Add explicit format instruction"}]'
    )
    agent = _agent(sample)
    inp = PromptReviewInput(
        prompt_text="Check this code and tell me if there are bugs.",
        expected_output_format="json",
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.blocker_count == 1
    assert res.findings[0].rule == "Prompt:format-unspecified"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_prompt_review_blocker_injection_vector():
    sample = (
        '[{"location":"prompt","severity":"blocker","rule":"Prompt:injection-vector",'
        '"message":"User input interpolated with no boundary","suggestion":"Add delimiters"}]'
    )
    agent = _agent(sample)
    inp = PromptReviewInput(
        prompt_text="Review this text: {user_input}. Return JSON.",
        source_location="agent_sdlc/agents/foo.py:42",
    )
    res = agent.run(inp)
    assert res.approved is False
    assert res.findings[0].rule == "Prompt:injection-vector"
    assert res.findings[0].severity == FindingSeverity.BLOCKER


def test_prompt_review_warning_no_role():
    sample = (
        '[{"location":"prompt","severity":"warning","rule":"Prompt:no-role",'
        '"message":"No role framing present","suggestion":"Add You are a ... opener"}]'
    )
    agent = _agent(sample)
    inp = PromptReviewInput(prompt_text="Check the diff. Return JSON array.")
    res = agent.run(inp)
    assert res.approved is True  # warnings don't block
    assert res.warning_count == 1
    assert res.findings[0].rule == "Prompt:no-role"


def test_prompt_review_warning_missing_fallback():
    sample = (
        '[{"location":"prompt","severity":"warning","rule":"Prompt:missing-fallback",'
        '"message":"No empty-list fallback","suggestion":"Add Return [] if no findings"}]'
    )
    agent = _agent(sample)
    inp = PromptReviewInput(
        prompt_text="You are a reviewer. Return a JSON array of issues."
    )
    res = agent.run(inp)
    assert res.approved is True
    assert res.findings[0].rule == "Prompt:missing-fallback"


def test_prompt_review_suggestion_example_missing():
    sample = (
        '[{"location":"prompt","severity":"suggestion","rule":"Prompt:example-missing",'
        '"message":"No few-shot example","suggestion":"Add an example input/output pair"}]'
    )
    agent = _agent(sample)
    inp = PromptReviewInput(
        prompt_text="You are a code reviewer. "
        + "x" * 200
        + " Return JSON array. Return [] if none."
    )
    res = agent.run(inp)
    assert res.approved is True
    assert res.suggestion_count == 1
    assert res.findings[0].rule == "Prompt:example-missing"


def test_prompt_review_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"prompt","severity":"suggestion","rule":"Prompt:example-missing","message":"No example"},'
        '{"location":"prompt","severity":"blocker","rule":"Prompt:format-unspecified","message":"No format"},'
        '{"location":"prompt","severity":"warning","rule":"Prompt:no-role","message":"No role"}'
        "]"
    )
    agent = _agent(sample)
    inp = PromptReviewInput(prompt_text="Check this.")
    res = agent.run(inp)
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_prompt_review_input_optional_fields_default_none():
    inp = PromptReviewInput(prompt_text="Hello.")
    assert inp.source_location is None
    assert inp.expected_output_format is None
    assert inp.agent_name is None


def test_prompt_review_counts():
    sample = (
        "["
        '{"location":"p","severity":"blocker","rule":"Prompt:format-unspecified","message":"a"},'
        '{"location":"p","severity":"blocker","rule":"Prompt:injection-vector","message":"b"},'
        '{"location":"p","severity":"warning","rule":"Prompt:no-role","message":"c"},'
        '{"location":"p","severity":"suggestion","rule":"Prompt:example-missing","message":"d"}'
        "]"
    )
    agent = _agent(sample)
    inp = PromptReviewInput(prompt_text="x")
    res = agent.run(inp)
    assert res.blocker_count == 2
    assert res.warning_count == 1
    assert res.suggestion_count == 1
    assert res.approved is False
