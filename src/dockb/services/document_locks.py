"""Per-document lock registry: one writer-preferring read/write lock per document.

A document's structural mutations (rename, renumber, delete) must never interleave
with a save of its chapters. Each document's lock lets callers hold it *exclusively*
(structural) or *shared* (saves); distinct documents stay independent. Entries are
evicted once no holder remains, so the registry does not grow with the number of
documents a server has seen.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class _ReadWriteLock:
    """A writer-preferring read/write lock guarding one document."""

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.Lock())
        self._readers = 0
        self._writer = False
        self._waiting_writers = 0

    def acquire_shared(self) -> None:
        """Block until no writer holds or waits, then take a reader slot."""
        with self._condition:
            while self._writer or self._waiting_writers > 0:
                self._condition.wait()
            self._readers += 1

    def release_shared(self) -> None:
        """Release one reader slot, waking queued holders when the last leaves."""
        with self._condition:
            self._readers -= 1
            if self._readers == 0:
                self._condition.notify_all()

    def acquire_exclusive(self) -> None:
        """Queue as a writer, then block until the document is entirely idle."""
        with self._condition:
            self._waiting_writers += 1
            try:
                while self._writer or self._readers > 0:
                    self._condition.wait()
            finally:
                self._waiting_writers -= 1
            self._writer = True

    def release_exclusive(self) -> None:
        """Release the writer, waking queued holders."""
        with self._condition:
            self._writer = False
            self._condition.notify_all()


class DocumentLocks:
    """Registry of per-document ``_ReadWriteLock`` objects with idle eviction."""

    def __init__(self) -> None:
        self._registry_guard = threading.Lock()
        self._locks: dict[str, tuple[_ReadWriteLock, int]] = {}

    def _take(self, document_id: str) -> _ReadWriteLock:
        """Return *document_id*'s lock, counting the caller as a user until release."""
        with self._registry_guard:
            entry = self._locks.get(document_id)
            if entry is None:
                entry = (_ReadWriteLock(), 0)
            lock, users = entry
            self._locks[document_id] = (lock, users + 1)
            return lock

    def _put_back(self, document_id: str, lock: _ReadWriteLock) -> None:
        """Drop *document_id*'s entry once no user (holder or waiter) remains."""
        with self._registry_guard:
            _, users = self._locks[document_id]
            if users <= 1:
                del self._locks[document_id]
            else:
                self._locks[document_id] = (lock, users - 1)

    @contextmanager
    def exclusive(self, document_id: str) -> Iterator[None]:
        """Hold *document_id*'s lock exclusively for the block's duration."""
        lock = self._take(document_id)
        lock.acquire_exclusive()
        try:
            yield
        finally:
            lock.release_exclusive()
            self._put_back(document_id, lock)

    @contextmanager
    def shared(self, document_id: str) -> Iterator[None]:
        """Hold *document_id*'s lock shared for the block's duration."""
        lock = self._take(document_id)
        lock.acquire_shared()
        try:
            yield
        finally:
            lock.release_shared()
            self._put_back(document_id, lock)
