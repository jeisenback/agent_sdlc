import os
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="E2E tests skipped unless RUN_E2E=1",
)


def test_postgres_integration():
    try:
        from testcontainers.postgres import PostgresContainer
    except Exception:
        pytest.skip("testcontainers not installed")

    from agent_sdlc.core.sqlalchemy_adapter import SqlAlchemyAdapter

    with PostgresContainer("postgres:15") as pg:
        url = pg.get_connection_url()
        adapter = SqlAlchemyAdapter(url)
        adapter.execute("CREATE TABLE IF NOT EXISTS items (id SERIAL PRIMARY KEY, name TEXT)")
        adapter.execute("INSERT INTO items (name) VALUES (:n)", {"n": "item1"})
        rows = adapter.fetchall("SELECT id, name FROM items")
        assert any(r[1] == "item1" for r in rows)
        adapter.close()
