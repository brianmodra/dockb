"""A thread-safe shell around one shared neo4j session.

A neo4j session is bound to one pooled connection and is not thread-safe: two
threads running one session interleave the bolt protocol and corrupt the
connection — a BufferError mid-read, defunct sockets, and follow-up requests
dying with ``RunMessage cannot be handled ... AUTO_COMMIT``.

This app wires a single session through every repository — request handlers on
FastAPI's threadpool, MCP tool calls arriving over several transports, and the
daemon-thread mentions jobs — so the shared session is guarded here: one query
with its full consumption runs at a time, and the lock is released as soon as
the driver has answered, so a slow caller (an LLM evaluation, say) between
queries cannot block anybody else's milliseconds-long statement.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol


class SessionLike(Protocol):
    """What every repository's session does: run, transact, and be closable.

    The app's repositories are normally handed a bare neo4j session; the
    shared-session wiring hands them a :class:`SerializedSession` instead, so
    the annotations accept either shape.
    """

    def run(self, query: str, parameters: Any = None, **kwargs: Any) -> Any:
        """One query; a bare session answers the driver's own streaming result."""

    def begin_transaction(self, *args: Any, **kwargs: Any) -> Any:
        """One managed transaction, entered with a with-block."""


class SerializedSession:
    """The decorated session every repository works through."""

    def __init__(self, session: Any) -> None:
        """Guard *session* — the shared pool-backed neo4j session."""
        self._session = session
        self._lock = threading.RLock()

    def run(self, query: str, parameters: Any = None, **kwargs: Any) -> list[Any]:
        """One query, start-to-finish under the lock, rows fully buffered."""
        with self._lock:
            return list(self._session.run(query, parameters, **kwargs))

    def begin_transaction(self, *args: Any, **kwargs: Any) -> _SerializedTransaction:
        """The managed transaction whose whole with-block holds the lock."""
        return _SerializedTransaction(self._lock, lambda: self._session.begin_transaction(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


class _SerializedTransaction:
    """A managed transaction that keeps the query lock while a caller is inside it."""

    def __init__(self, lock: threading.RLock, opener: Callable[[], Any]) -> None:
        """Hold *lock* and open the transaction through *opener* on entry."""
        self._lock = lock
        self._opener = opener
        self._tx: Any = None

    def __enter__(self) -> _SerializedTransaction:
        """Open the raw managed transaction, the lock now held."""
        self._lock.acquire()
        try:
            self._tx = self._opener()
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close (or roll back) the transaction, then give the lock back."""
        try:
            self._tx.__exit__(*exc_info)
        finally:
            self._lock.release()

    def run(self, query: str, parameters: Any = None, **kwargs: Any) -> Any:
        """One statement inside the open transaction."""
        with self._lock:
            return self._tx.run(query, parameters, **kwargs)

    def commit(self) -> Any:
        """Commit the open transaction to the database."""
        return self._tx.commit()

    def rollback(self) -> Any:
        """Roll back the open transaction's statements."""
        return self._tx.rollback()
