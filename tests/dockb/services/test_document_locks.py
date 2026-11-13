"""Tests for the per-document lock registry."""

import threading
import time

from dockb.services.document_locks import DocumentLocks

_JOIN_TIMEOUT = 5.0


class TestDocumentLocks:  # pylint: disable=too-many-public-methods
    def test_exclusive_blocks_exclusive(self) -> None:
        locks = DocumentLocks()
        acquired = threading.Event()
        proceed = threading.Event()

        def holder() -> None:
            with locks.exclusive("d1"):
                acquired.set()
                proceed.wait(_JOIN_TIMEOUT)

        t1 = threading.Thread(target=holder)
        t1.start()
        assert acquired.wait(_JOIN_TIMEOUT)

        order: list[str] = []

        def contender() -> None:
            with locks.exclusive("d1"):
                order.append("second")

        t2 = threading.Thread(target=contender)
        t2.start()
        t2.join(timeout=0.2)
        assert not order

        proceed.set()
        t1.join(_JOIN_TIMEOUT)
        t2.join(_JOIN_TIMEOUT)
        assert order == ["second"]
        assert not t1.is_alive() and not t2.is_alive()

    def test_exclusive_blocks_shared(self) -> None:
        locks = DocumentLocks()
        acquired = threading.Event()
        proceed = threading.Event()

        def holder() -> None:
            with locks.exclusive("d1"):
                acquired.set()
                proceed.wait(_JOIN_TIMEOUT)

        t1 = threading.Thread(target=holder)
        t1.start()
        assert acquired.wait(_JOIN_TIMEOUT)

        order: list[str] = []

        def reader() -> None:
            with locks.shared("d1"):
                order.append("reader")

        t2 = threading.Thread(target=reader)
        t2.start()
        t2.join(timeout=0.2)
        assert not order

        proceed.set()
        t1.join(_JOIN_TIMEOUT)
        t2.join(_JOIN_TIMEOUT)
        assert order == ["reader"]
        assert not t1.is_alive() and not t2.is_alive()

    def test_shared_runs_concurrently(self) -> None:
        locks = DocumentLocks()
        inside = 0
        inside_guard = threading.Lock()
        both = threading.Event()
        release = threading.Event()

        def reader() -> None:
            nonlocal inside
            with locks.shared("d1"):
                with inside_guard:
                    inside += 1
                    if inside == 2:
                        both.set()
                release.wait(_JOIN_TIMEOUT)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        assert both.wait(_JOIN_TIMEOUT)
        release.set()
        t1.join(_JOIN_TIMEOUT)
        t2.join(_JOIN_TIMEOUT)
        assert not t1.is_alive() and not t2.is_alive()

    def test_distinct_documents_are_independent(self) -> None:
        locks = DocumentLocks()
        acquired = threading.Event()
        proceed = threading.Event()

        def holder() -> None:
            with locks.exclusive("d1"):
                acquired.set()
                proceed.wait(_JOIN_TIMEOUT)

        t1 = threading.Thread(target=holder)
        t1.start()
        assert acquired.wait(_JOIN_TIMEOUT)

        other_done = threading.Event()

        def other() -> None:
            with locks.exclusive("d2"):
                other_done.set()

        t2 = threading.Thread(target=other)
        t2.start()
        assert other_done.wait(_JOIN_TIMEOUT)

        proceed.set()
        t1.join(_JOIN_TIMEOUT)
        t2.join(_JOIN_TIMEOUT)

    def test_registry_evicts_idle_entries(self) -> None:
        locks = DocumentLocks()
        with locks.exclusive("d1"):
            assert "d1" in locks._locks  # pylint: disable=protected-access
        assert "d1" not in locks._locks  # pylint: disable=protected-access

    def test_shared_then_exclusive_on_the_same_document_serialize(self) -> None:
        locks = DocumentLocks()

        def reader() -> None:
            with locks.shared("d1"):
                time.sleep(0.05)

        def writer() -> None:
            with locks.exclusive("d1"):
                pass

        threads = [threading.Thread(target=reader) for _ in range(3)] + [threading.Thread(target=writer)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(_JOIN_TIMEOUT)
        assert not any(t.is_alive() for t in threads)

    def test_a_waiting_writer_is_preferred_over_a_late_reader(self) -> None:
        locks = DocumentLocks()
        reader_acquired = threading.Event()
        release_first = threading.Event()

        def first_reader() -> None:
            with locks.shared("d1"):
                reader_acquired.set()
                release_first.wait(_JOIN_TIMEOUT)

        t1 = threading.Thread(target=first_reader)
        t1.start()
        assert reader_acquired.wait(_JOIN_TIMEOUT)

        order: list[str] = []

        def writer() -> None:
            with locks.exclusive("d1"):
                order.append("writer")

        t2 = threading.Thread(target=writer)
        t2.start()

        # Wait until the writer is actually queued behind the active reader before
        # admitting a late reader, so the queue preference is what decides the order.
        rwlock = locks._locks["d1"][0]  # pylint: disable=protected-access
        deadline = time.time() + _JOIN_TIMEOUT
        while rwlock._waiting_writers == 0 and time.time() < deadline:  # pylint: disable=protected-access
            time.sleep(0.01)
        assert rwlock._waiting_writers == 1  # pylint: disable=protected-access

        def late_reader() -> None:
            with locks.shared("d1"):
                order.append("reader")

        t3 = threading.Thread(target=late_reader)
        t3.start()

        release_first.set()
        for t in (t1, t2, t3):
            t.join(_JOIN_TIMEOUT)
        assert order == ["writer", "reader"]
