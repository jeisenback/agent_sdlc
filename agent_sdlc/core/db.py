from __future__ import annotations
from typing import Protocol, Iterable, List, Tuple, Optional, ContextManager
import sqlite3
import threading
from contextlib import contextmanager


class DBAdapter(Protocol):
    def connect(self) -> None: ...

    def execute(self, sql: str, params: Optional[Iterable] = None) -> int: ...

    def fetchall(self, sql: str, params: Optional[Iterable] = None) -> List[Tuple]: ...

    def close(self) -> None: ...

    @contextmanager
    def transaction(self) -> ContextManager: ...


class SqliteAdapter:
    """Simple sqlite adapter implementing the minimal DBAdapter contract.

    Uses a thread-safe connection instance (check_same_thread=False) and a reentrant lock to
    guard concurrent access in tests.
    """

    def __init__(self, url: str = ":memory:", timeout: float = 5.0):
        self.url = url
        self.timeout = float(timeout)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self.url, check_same_thread=False, timeout=self.timeout)
            self._conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: Optional[Iterable] = None) -> int:
        self.connect()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(params) if params else ())
            self._conn.commit()
            return cur.rowcount

    def fetchall(self, sql: str, params: Optional[Iterable] = None) -> List[Tuple]:
        self.connect()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, tuple(params) if params else ())
            rows = cur.fetchall()
            return [tuple(r) for r in rows]

    @contextmanager
    def transaction(self):
        self.connect()
        with self._lock:
            try:
                yield
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
