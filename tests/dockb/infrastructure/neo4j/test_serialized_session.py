"""Tests for the serialized shared session (thread-safe single-session wiring)."""

from __future__ import annotations

import threading
import time
from typing import Any

from dockb.infrastructure.neo4j.serialized_session import SerializedSession


class _RecordingTransaction:
    def run(self, query: str, params: Any = None, **kwargs: Any) -> Any:
        return self._session.run(query, params, **kwargs)

    def __init__(self, session: _RecordingSession) -> None:
        self._session = session

    def commit(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> None:
        return None


class _RecordingSession:
    """A fake session that fails when two queries overlap."""

    def __init__(self) -> None:
        self.active = 0
        self.queries: list[str] = []
        self.overlaps = 0
        self.closed = False

    def run(self, query: str, _params: Any = None, **_kwargs: Any) -> Any:
        if self.active > 0:
            self.overlaps += 1
        self.active += 1
        try:
            time.sleep(0.02)
            self.queries.append(query)
            return [f"row:{len(self.queries)}"]
        finally:
            self.active -= 1

    def begin_transaction(self, *_args: Any, **_kwargs: Any) -> _RecordingTransaction:
        return _RecordingTransaction(self)

    def close(self) -> None:
        self.closed = True


def test_concurrent_queries_never_overlap() -> None:
    raw = _RecordingSession()
    session = SerializedSession(raw)

    def user() -> None:
        for _ in range(5):
            session.run("query")

    threads = [threading.Thread(target=user) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert raw.overlaps == 0
    assert len(raw.queries) == 20


def test_run_answers_the_fully_consumed_rows() -> None:
    raw = _RecordingSession()
    session = SerializedSession(raw)
    assert session.run("query", {"a": 1}) == ["row:1"]


def test_a_transaction_holds_the_query_lock_until_it_is_left() -> None:
    raw = _RecordingSession()
    session = SerializedSession(raw)
    started = threading.Event()
    thread_complete = threading.Event()

    def other() -> None:
        started.set()
        session.run("two")
        thread_complete.set()

    with session.begin_transaction() as tx:
        tx.run("one")
        thread = threading.Thread(target=other)
        thread.start()
        assert started.wait(1)
        # the other query is still waiting on the lock the transaction holds
        thread.join(0.05)
        assert thread.is_alive()
    thread.join()

    assert thread_complete.is_set()
    assert raw.overlaps == 0
    assert raw.queries == ["one", "two"]


def test_unknown_attributes_reach_the_raw_session() -> None:
    raw = _RecordingSession()
    session = SerializedSession(raw)
    session.close()
    assert raw.closed is True
