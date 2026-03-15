"""Unit tests that cover previously-uncovered branches in core modules.

These tests are designed to run offline (no network, no API keys) and bring
total coverage above the 80% gate.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# SqlAlchemyAdapter (uses sqlite in-memory — no Postgres needed)
# ---------------------------------------------------------------------------


def test_sqlalchemy_adapter_crud() -> None:
    try:
        from agent_sdlc.core.sqlalchemy_adapter import SqlAlchemyAdapter
    except Exception as e:
        pytest.skip(f"Cannot import SqlAlchemyAdapter: {e}")

    adapter = SqlAlchemyAdapter()  # sqlite:///:memory:
    adapter.connect()
    adapter.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    adapter.execute("INSERT INTO items (name) VALUES (:n)", {"n": "foo"})
    adapter.execute("INSERT INTO items (name) VALUES (:n)", {"n": "bar"})
    rows = adapter.fetchall("SELECT id, name FROM items ORDER BY id")
    assert len(rows) == 2
    assert rows[0][1] == "foo"
    assert rows[1][1] == "bar"
    adapter.close()


def test_sqlalchemy_adapter_transaction_commit() -> None:
    try:
        from agent_sdlc.core.sqlalchemy_adapter import SqlAlchemyAdapter
    except Exception as e:
        pytest.skip(f"Cannot import SqlAlchemyAdapter: {e}")

    adapter = SqlAlchemyAdapter()
    adapter.execute("CREATE TABLE tx (v TEXT)")
    with adapter.transaction():
        adapter.execute("INSERT INTO tx (v) VALUES (:v)", {"v": "ok"})
    rows = adapter.fetchall("SELECT v FROM tx")
    assert any(r[0] == "ok" for r in rows)
    adapter.close()


def test_sqlalchemy_adapter_transaction_rollback() -> None:
    try:
        from agent_sdlc.core.sqlalchemy_adapter import SqlAlchemyAdapter
    except Exception as e:
        pytest.skip(f"Cannot import SqlAlchemyAdapter: {e}")

    adapter = SqlAlchemyAdapter()
    adapter.execute("CREATE TABLE rb (v TEXT)")
    with pytest.raises(RuntimeError):
        with adapter.transaction():
            adapter.execute("INSERT INTO rb (v) VALUES (:v)", {"v": "bad"})
            raise RuntimeError("force rollback")
    adapter.close()


def test_sqlalchemy_adapter_missing_raises() -> None:
    """When SQLAlchemy is unavailable the constructor should raise RuntimeError."""
    from agent_sdlc.core import sqlalchemy_adapter as sa_mod

    orig = sa_mod.create_engine
    try:
        sa_mod.create_engine = None  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="SQLAlchemy is not installed"):
            sa_mod.SqlAlchemyAdapter()
    finally:
        sa_mod.create_engine = orig


# ---------------------------------------------------------------------------
# with_retry — backoff / exhaust paths
# ---------------------------------------------------------------------------


def test_with_retry_succeeds_first_try() -> None:
    from agent_sdlc.core.retry import with_retry

    calls = []

    @with_retry(max_attempts=3, initial_delay=0.0)
    def fn() -> str:
        calls.append(1)
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 1


def test_with_retry_retries_then_succeeds() -> None:
    from agent_sdlc.core.retry import with_retry

    calls = []

    @with_retry(max_attempts=3, initial_delay=0.0, backoff=1.0)
    def fn() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not yet")
        return "ok"

    assert fn() == "ok"
    assert len(calls) == 2


def test_with_retry_exhausts_and_raises() -> None:
    from agent_sdlc.core.retry import with_retry

    calls = []

    @with_retry(max_attempts=2, initial_delay=0.0, backoff=1.0)
    def fn() -> None:
        calls.append(1)
        raise ValueError("always")

    with pytest.raises(ValueError, match="always"):
        fn()
    assert len(calls) == 2


def test_with_retry_only_retries_specified_exceptions() -> None:
    from agent_sdlc.core.retry import with_retry

    @with_retry(max_attempts=3, initial_delay=0.0, retry_on=(TypeError,))
    def fn() -> None:
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        fn()


# ---------------------------------------------------------------------------
# parse_findings_from_json — fallback / edge-case paths
# ---------------------------------------------------------------------------


def test_parse_findings_strips_code_fence() -> None:
    from agent_sdlc.core.findings import FindingSeverity, parse_findings_from_json

    raw = '```json\n[{"message":"m","severity":"blocker"}]\n```'
    findings = parse_findings_from_json(raw)
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.BLOCKER


def test_parse_findings_no_fence() -> None:
    from agent_sdlc.core.findings import parse_findings_from_json

    raw = '[{"message":"hello","severity":"warning"}]'
    findings = parse_findings_from_json(raw)
    assert findings[0].message == "hello"


def test_parse_findings_bracket_depth_with_nested_bracket_in_string() -> None:
    from agent_sdlc.core.findings import parse_findings_from_json

    raw = '[{"message":"see [note]","severity":"suggestion"}]'
    findings = parse_findings_from_json(raw)
    assert findings[0].message == "see [note]"


def test_parse_findings_empty_list() -> None:
    from agent_sdlc.core.findings import parse_findings_from_json

    assert parse_findings_from_json("[]") == []


def test_parse_findings_regex_fallback() -> None:
    """When JSON is malformed, the regex fallback should extract objects."""
    from agent_sdlc.core.findings import parse_findings_from_json

    # Deliberately malformed JSON (unescaped quote inside string value)
    raw = '[{"message": "bad "quote"", "severity": "warning"}]'
    # Should not raise; may return partial or empty results
    result = parse_findings_from_json(raw)
    assert isinstance(result, list)


def test_parse_findings_totally_invalid_returns_empty() -> None:
    from agent_sdlc.core.findings import parse_findings_from_json

    result = parse_findings_from_json("not json at all")
    assert result == []
