import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Integration tests skipped unless RUN_INTEGRATION=1",
)


def test_sqlalchemy_adapter_basic():
    try:
        from agent_sdlc.core.sqlalchemy_adapter import SqlAlchemyAdapter
    except Exception as e:
        pytest.skip(f"Unable to import adapter: {e}")

    # prefer a file-backed sqlite DB for cross-connection persistence
    db_path = ".tmp_sqlalchemy_test.db"
    url = f"sqlite:///{db_path}"

    try:
        try:
            adapter = SqlAlchemyAdapter(url)
        except RuntimeError as e:
            pytest.skip(f"SQLAlchemy not available: {e}")

        adapter.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, val TEXT)")
        adapter.execute("INSERT INTO t (val) VALUES (:v)", {"v": "a"})
        rows = adapter.fetchall("SELECT id, val FROM t")
        assert len(rows) >= 1
        assert any(r[1] == "a" for r in rows)
    finally:
        try:
            adapter.close()
        except Exception:
            pass
        try:
            os.remove(db_path)
        except Exception:
            pass
