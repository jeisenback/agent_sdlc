import pytest

from agent_sdlc.agents.traceability import (
    TraceabilityChecker,
    TraceabilityInput,
    TraceabilityResult,
)
from agent_sdlc.core.findings import FindingSeverity

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _checker(inp: TraceabilityInput) -> TraceabilityChecker:
    return TraceabilityChecker(inp)


def _run(inp: TraceabilityInput) -> TraceabilityResult:
    return _checker(inp).run()


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_raises_when_no_pr_or_issue():
    with pytest.raises(ValueError, match="pr_number or issue_number required"):
        TraceabilityChecker(TraceabilityInput())


def test_constructor_ok_with_pr_number():
    checker = TraceabilityChecker(TraceabilityInput(pr_number=1))
    assert checker is not None


def test_constructor_ok_with_issue_number():
    checker = TraceabilityChecker(TraceabilityInput(issue_number=1))
    assert checker is not None


# ---------------------------------------------------------------------------
# trace:pr-no-issue
# ---------------------------------------------------------------------------


def test_pr_no_issue_warning_when_no_closes():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="This PR adds retry logic.",
    )
    res = _run(inp)
    rules = [f.rule for f in res.findings]
    assert "trace:pr-no-issue" in rules
    f = next(f for f in res.findings if f.rule == "trace:pr-no-issue")
    assert f.severity == FindingSeverity.WARNING
    assert res.passed is False


def test_pr_no_issue_not_raised_when_closes_present():
    for body in [
        "Closes #42\n\nAdds retry.",
        "Fixes #7 — resolves the crash.",
        "Resolves #100",
        "Refs #5 for context",
        "refs #5",
    ]:
        inp = TraceabilityInput(pr_number=1, pr_body=body)
        res = _run(inp)
        assert not any(f.rule == "trace:pr-no-issue" for f in res.findings), body


def test_pr_no_issue_skipped_when_pr_body_is_none():
    inp = TraceabilityInput(pr_number=1, pr_body=None)
    res = _run(inp)
    assert not any(f.rule == "trace:pr-no-issue" for f in res.findings)


# ---------------------------------------------------------------------------
# trace:issue-no-requirement
# ---------------------------------------------------------------------------


def test_issue_no_requirement_suggestion_when_no_link():
    inp = TraceabilityInput(
        issue_number=8,
        issue_body="We should add a feature.",
    )
    res = _run(inp)
    rules = [f.rule for f in res.findings]
    assert "trace:issue-no-requirement" in rules
    f = next(f for f in res.findings if f.rule == "trace:issue-no-requirement")
    assert f.severity == FindingSeverity.SUGGESTION
    # suggestions don't affect passed
    assert res.passed is True


def test_issue_no_requirement_not_raised_when_requirements_md_linked():
    inp = TraceabilityInput(
        issue_number=8,
        issue_body="See REQUIREMENTS.md section 3 for AC.",
    )
    res = _run(inp)
    assert not any(f.rule == "trace:issue-no-requirement" for f in res.findings)


def test_issue_no_requirement_not_raised_when_requirements_section_present():
    inp = TraceabilityInput(
        issue_number=8,
        issue_body="## Requirements\n- Must handle timeouts",
    )
    res = _run(inp)
    assert not any(f.rule == "trace:issue-no-requirement" for f in res.findings)


def test_issue_no_requirement_skipped_when_issue_body_is_none():
    inp = TraceabilityInput(issue_number=8, issue_body=None)
    res = _run(inp)
    assert not any(f.rule == "trace:issue-no-requirement" for f in res.findings)


# ---------------------------------------------------------------------------
# trace:pr-no-tests
# ---------------------------------------------------------------------------


def test_pr_no_tests_warning_when_source_changed_no_tests():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="Closes #1",
        changed_files=["agent_sdlc/core/retry.py", "agent_sdlc/agents/pr_review.py"],
        test_files_changed=[],
    )
    res = _run(inp)
    rules = [f.rule for f in res.findings]
    assert "trace:pr-no-tests" in rules
    f = next(f for f in res.findings if f.rule == "trace:pr-no-tests")
    assert f.severity == FindingSeverity.WARNING
    assert res.passed is False


def test_pr_no_tests_not_raised_when_tests_in_test_files_changed():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="Closes #1",
        changed_files=["agent_sdlc/core/retry.py"],
        test_files_changed=["tests/test_retry.py"],
    )
    res = _run(inp)
    assert not any(f.rule == "trace:pr-no-tests" for f in res.findings)


def test_pr_no_tests_not_raised_when_test_in_changed_files():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="Closes #1",
        changed_files=["agent_sdlc/core/retry.py", "tests/test_retry.py"],
        test_files_changed=[],
    )
    res = _run(inp)
    assert not any(f.rule == "trace:pr-no-tests" for f in res.findings)


def test_pr_no_tests_not_raised_when_only_non_source_changed():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="Closes #1",
        changed_files=["README.md", "docs/agents.md"],
        test_files_changed=[],
    )
    res = _run(inp)
    assert not any(f.rule == "trace:pr-no-tests" for f in res.findings)


# ---------------------------------------------------------------------------
# Happy path — fully linked PR passes
# ---------------------------------------------------------------------------


def test_fully_linked_pr_passes():
    inp = TraceabilityInput(
        pr_number=42,
        pr_body="Closes #7\n\nAdds retry logic.",
        issue_number=7,
        issue_body="See REQUIREMENTS.md for acceptance criteria.",
        changed_files=["agent_sdlc/core/retry.py", "tests/test_retry.py"],
        test_files_changed=["tests/test_retry.py"],
    )
    res = _run(inp)
    assert res.findings == [] or all(
        f.severity == FindingSeverity.SUGGESTION for f in res.findings
    )
    assert res.passed is True


# ---------------------------------------------------------------------------
# passed property
# ---------------------------------------------------------------------------


def test_passed_false_on_warning():
    inp = TraceabilityInput(pr_number=1, pr_body="No issue link here.")
    res = _run(inp)
    assert res.passed is False


def test_passed_true_when_only_suggestions():
    inp = TraceabilityInput(
        issue_number=8,
        issue_body="No requirements link.",
    )
    res = _run(inp)
    # Only suggestion — passed should still be True
    assert res.passed is True
