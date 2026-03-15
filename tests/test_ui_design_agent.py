from agent_sdlc.agents.ui_design import UIDesignAgent, UIDesignInput
from agent_sdlc.core.findings import FindingSeverity
from agent_sdlc.core.providers import DummyLLMProvider
from scripts.run_ui_design import _heuristic_checks


def _agent(response: str = "[]") -> UIDesignAgent:
    return UIDesignAgent(DummyLLMProvider(default=response))


def _inp(**kwargs) -> UIDesignInput:  # type: ignore[no-untyped-def]
    defaults = dict(artifact="<div>hello</div>", artifact_type="html")
    defaults.update(kwargs)
    return UIDesignInput(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_ui_approved_when_no_findings():
    res = _agent("[]").run(_inp())
    assert res.findings == []
    assert res.approved is True
    assert res.blocker_count == 0


# ---------------------------------------------------------------------------
# BLOCKER rules (LLM path)
# ---------------------------------------------------------------------------


def test_ui_blocker_missing_alt_text():
    sample = (
        '[{"location":"<img src=logo.png>","severity":"blocker","rule":"UI:missing-alt-text",'
        '"message":"img has no alt attribute","suggestion":"Add alt text"}]'
    )
    res = _agent(sample).run(_inp(artifact='<img src="logo.png">'))
    assert res.approved is False
    assert res.blocker_count == 1
    f = res.findings[0]
    assert f.rule == "UI:missing-alt-text"
    assert f.severity == FindingSeverity.BLOCKER


def test_ui_blocker_color_contrast():
    sample = (
        '[{"location":"p.text","severity":"blocker","rule":"UI:color-contrast",'
        '"message":"#ccc on #fff fails WCAG AA","suggestion":"Use #767676 or darker"}]'
    )
    res = _agent(sample).run(_inp(artifact='<p style="color:#ccc">text</p>'))
    assert res.approved is False
    f = res.findings[0]
    assert f.rule == "UI:color-contrast"
    assert f.severity == FindingSeverity.BLOCKER


# ---------------------------------------------------------------------------
# WARNING rules
# ---------------------------------------------------------------------------


def test_ui_warning_hardcoded_color():
    sample = (
        '[{"location":"div","severity":"warning","rule":"UI:hardcoded-color",'
        '"message":"Literal #ff0000 used","suggestion":"Use --color-danger CSS variable"}]'
    )
    res = _agent(sample).run(_inp(artifact='<div style="color:#ff0000">'))
    assert res.approved is True
    assert res.warning_count == 1
    assert res.findings[0].rule == "UI:hardcoded-color"


def test_ui_warning_responsive_missing():
    sample = (
        '[{"location":".container","severity":"warning","rule":"UI:responsive-missing",'
        '"message":"Fixed 800px width with no breakpoint","suggestion":"Add max-width and media query"}]'
    )
    res = _agent(sample).run(
        _inp(artifact=".container { width: 800px; }", artifact_type="css")
    )
    assert res.approved is True
    assert res.findings[0].rule == "UI:responsive-missing"


# ---------------------------------------------------------------------------
# SUGGESTION rules
# ---------------------------------------------------------------------------


def test_ui_suggestion_z_index_magic():
    sample = (
        '[{"location":".modal","severity":"suggestion","rule":"UI:z-index-magic",'
        '"message":"z-index: 9999 without comment","suggestion":"Add stacking context comment"}]'
    )
    res = _agent(sample).run(
        _inp(artifact=".modal { z-index: 9999; }", artifact_type="css")
    )
    assert res.approved is True
    assert res.suggestion_count == 1
    assert res.findings[0].rule == "UI:z-index-magic"


# ---------------------------------------------------------------------------
# Sort order and counts
# ---------------------------------------------------------------------------


def test_ui_findings_sorted_blockers_first():
    sample = (
        "["
        '{"location":"a","severity":"suggestion","rule":"UI:z-index-magic","message":"z"},'
        '{"location":"b","severity":"blocker","rule":"UI:missing-alt-text","message":"alt"},'
        '{"location":"c","severity":"warning","rule":"UI:hardcoded-color","message":"color"}'
        "]"
    )
    res = _agent(sample).run(_inp())
    assert res.findings[0].severity == FindingSeverity.BLOCKER
    assert res.findings[1].severity == FindingSeverity.WARNING
    assert res.findings[2].severity == FindingSeverity.SUGGESTION


def test_ui_counts():
    sample = (
        "["
        '{"location":"a","severity":"blocker","rule":"UI:missing-alt-text","message":"a"},'
        '{"location":"b","severity":"blocker","rule":"UI:color-contrast","message":"b"},'
        '{"location":"c","severity":"warning","rule":"UI:hardcoded-color","message":"c"},'
        '{"location":"d","severity":"suggestion","rule":"UI:z-index-magic","message":"d"}'
        "]"
    )
    res = _agent(sample).run(_inp())
    assert res.blocker_count == 2
    assert res.warning_count == 1
    assert res.suggestion_count == 1
    assert res.approved is False


# ---------------------------------------------------------------------------
# Heuristic checks (no LLM)
# ---------------------------------------------------------------------------


def test_heuristic_missing_alt_detected():
    source = '<img src="logo.png"><img src="icon.svg" alt="icon">'
    issues = _heuristic_checks(source, "test.html")
    rules = [r for r, _ in issues]
    assert "UI:missing-alt-text" in rules
    # Only the first img (no alt) should trigger
    assert rules.count("UI:missing-alt-text") == 1


def test_heuristic_missing_alt_not_triggered_when_alt_present():
    source = '<img src="logo.png" alt="Company logo">'
    issues = _heuristic_checks(source, "test.html")
    assert not any(r == "UI:missing-alt-text" for r, _ in issues)


def test_heuristic_hardcoded_color_detected():
    source = "color: #ff0000;"
    issues = _heuristic_checks(source, "test.css")
    assert any(r == "UI:hardcoded-color" for r, _ in issues)


def test_heuristic_hardcoded_color_not_triggered_on_css_var_declaration():
    source = "--color-danger: #ff0000;"
    issues = _heuristic_checks(source, "test.css")
    assert not any(r == "UI:hardcoded-color" for r, _ in issues)


def test_heuristic_rgb_detected():
    source = "background: rgb(255, 0, 0);"
    issues = _heuristic_checks(source, "test.css")
    assert any(r == "UI:hardcoded-color" for r, _ in issues)


def test_heuristic_no_issues_on_clean_source():
    source = '<div class="container"><img src="logo.png" alt="Logo"></div>'
    issues = _heuristic_checks(source, "test.html")
    assert issues == []


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


def test_ui_input_optional_fields_default_none():
    inp = UIDesignInput(artifact="x", artifact_type="html")
    assert inp.component_name is None
    assert inp.design_system is None
