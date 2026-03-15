from __future__ import annotations

from contextlib import contextmanager
from typing import ContextManager, Iterable, List, Optional, Tuple

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except Exception:  # pragma: no cover - optional dependency
    create_engine = None
    text = None
    Engine = object  # type: ignore

from .db import DBAdapter  # noqa: F401  re-exported for adapter consumers


class SqlAlchemyAdapter:
    """Lightweight SQLAlchemy-based adapter.

    SQLAlchemy is optional at runtime. This adapter raises a clear error when
    SQLAlchemy is not installed so higher-level code can opt into integration tests
    or production dependencies.
    """

    def __init__(self, url: str = "sqlite:///:memory:", **engine_kwargs) -> None:
        if create_engine is None:
            raise RuntimeError(
                "SQLAlchemy is not installed. Install sqlalchemy to use SqlAlchemyAdapter."
            )
        self.url = url
        self._engine: Engine = create_engine(url, **engine_kwargs)

    def connect(self) -> None:
        # Engine is ready; explicit connect is unnecessary for SQLAlchemy Engine.
        return None

    def execute(self, sql: str, params: Optional[Iterable] = None) -> int:
        if create_engine is None:
            raise RuntimeError("SQLAlchemy is not installed.")
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            try:
                # attempt to commit if the connection supports it
                conn.commit()
            except Exception:
                pass
            return getattr(result, "rowcount", 0) or 0

    def fetchall(self, sql: str, params: Optional[Iterable] = None) -> List[Tuple]:
        if create_engine is None:
            raise RuntimeError("SQLAlchemy is not installed.")
        with self._engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            rows = result.fetchall()
            return [tuple(r) for r in rows]

    @contextmanager
    def transaction(self) -> ContextManager:
        if create_engine is None:
            raise RuntimeError("SQLAlchemy is not installed.")
        conn = self._engine.connect()
        trans = conn.begin()
        try:
            yield
            trans.commit()
        except Exception:
            trans.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        try:
            self._engine.dispose()
        except Exception:
            pass
