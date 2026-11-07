"""The mentions scheduler: coalesce per-chapter evaluations, cancel superseded ones.

The save pipeline triggers a chapter's mention evaluation after each save; a
burst of saves must not become a burst of concurrent evaluations of the same
chapter. The scheduler keeps, per chapter id, at most one running evaluation
and one `dirty` flag: a trigger that arrives while the chapter's job is
running installs its own — freshest — job factory on the slot, cancels the
running job (cooperatively, at the job's own checkpoints), and the successor
the running worker ends up spawning builds through the newest factory. A
trigger that arrives while the chapter is idle starts a worker immediately.
The latest state is always evaluated eventually, and never twice at once.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from dockb.services.mentions import MentionsJob

JobFactory = Callable[[], MentionsJob]


def start_thread(target: Callable[[], None]) -> None:
    """Run the slot's worker *target* on a one-shot daemon thread; the caller never waits."""
    tagged = f"mentions-evaluation:{getattr(target, '__name__', 'worker')}"
    threading.Thread(target=target, name=tagged, daemon=True).start()


class _Entry:  # pylint: disable=too-few-public-methods
    """One chapter's slot: the running job's cancellation, and the freshest pending factory."""

    def __init__(self, factory: JobFactory) -> None:
        self.cancelled = threading.Event()
        self.factory = factory
        self.dirty = False


class MentionsScheduler:  # pylint: disable=too-few-public-methods
    """At most one running evaluation per chapter, always the latest state next."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._guard = threading.Lock()

    def schedule(self, chapter_id: str, make_job: JobFactory) -> None:
        """Evaluate *chapter_id* now, or cancel-and-queue when one is running.

        *make_job* builds a MentionsJob for exactly `chapter_id` — one chapter
        per slot — from the repositories as they are in the caller's hands; the
        trigger, not the scheduler, owns what the evaluation reads. When the
        chapter is idle the job is started at once. While the chapter's job is
        running, further triggers only mark the slot dirty, install their
        factory as the freshest, and cancel the running job, whose worker then
        runs the job that factory builds; nothing is evaluated twice at once.
        """
        with self._guard:
            entry = self._entries.get(chapter_id)
            if entry is not None:
                entry.dirty = True
                entry.factory = make_job
                entry.cancelled.set()
                return
            self._entries[chapter_id] = _Entry(make_job)
        self._start_worker(chapter_id)

    def _start_worker(self, chapter_id: str) -> None:
        start_thread(self._worker(chapter_id))

    def _worker(self, chapter_id: str) -> Callable[[], None]:
        def run() -> None:
            entry = self._entries[chapter_id]
            job = entry.factory()
            job.cancel = entry.cancelled
            try:
                job.run()
            finally:
                self._release(chapter_id)

        return run

    def _release(self, chapter_id: str) -> None:
        with self._guard:
            entry = self._entries.pop(chapter_id, None)
            if entry is None or not entry.dirty:
                return
            # the successor takes the slot before any schedule() between this
            # return and its worker starting can claim it as idle
            self._entries[chapter_id] = _Entry(entry.factory)
        self._start_worker(chapter_id)
