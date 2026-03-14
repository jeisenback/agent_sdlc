from agent_sdlc.core.db import SqliteAdapter


def test_sqlite_execute_fetch():
    db = SqliteAdapter()
    try:
        db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        count = db.execute("INSERT INTO test (name) VALUES (?)", ("alice",))
        # sqlite reports -1 for rowcount on some drivers; accept truthy
        assert count != 0
        rows = db.fetchall("SELECT id, name FROM test")
        assert rows[0][1] == "alice"
    finally:
        db.close()
