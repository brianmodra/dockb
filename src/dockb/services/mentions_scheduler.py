"""The mentions scheduler: coalesce evaluations, cancel superseded ones.

The save pipeline triggers a mention evaluation after each save; a burst of
saves must not become a burst of concurrent evaluations. One worker thread runs
the evaluations, in FIFO order, so two evaluations never overlap. Per trigger
the scheduler keeps at most one running job and one pending — freshest —
factory: a trigger that arrives while its key's job is running cancels the
running job (cooperatively, at the job's own checkpoints) and records the newest
factory as the successor, which the worker runs after the running job finishes.
A trigger that arrives while its key is already queued only refreshes the
factory, so a burst of saves queues the fresh state once, not once per save. The
latest state is always evaluated eventually, and never twice at once.

The key is the chapter whose save triggered the evaluation: a manuscript chapter
for its own evaluation, or a character chapter for a document-wide one.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Protocol

logger = logging.getLogger(__name__)


class EvaluationJob(Protocol):  # pylint: disable=too-few-public-methods
    """What the worker runs: a job with a cooperative cancel and a run."""

    cancel: threading.Event | None

    def run(self) -> None:
        """Do the evaluation."""


JobFactory = Callable[[], EvaluationJob]


def start_thread(target: Callable[[], None]) -> None:
    """Run the worker *target* on a one-shot daemon thread; the caller never waits."""
    tagged = f"mentions-evaluation:{getattr(target, '__name__', 'worker')}"
    threading.Thread(target=target, name=tagged, daemon=True).start()


class MentionsScheduler:  # pylint: disable=too-few-public-methods
    """At most one running evaluation per trigger, one worker in all."""

    def __init__(self) -> None:
        self._pending: dict[str, JobFactory] = {}
        self._running: dict[str, threading.Event] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._guard = threading.Lock()
        self._worker_alive = False

    def schedule(self, chapter_id: str, make_job: JobFactory) -> None:
        """Evaluate for *chapter_id* in turn, cancel-and-queue when one is running.

        *chapter_id* is the chapter whose save triggered the evaluation: a
        manuscript chapter evaluates itself, a character chapter evaluates its
        whole document. *make_job* builds the job from the repositories as they
        are in the caller's hands; the trigger, not the scheduler, owns what the
        evaluation reads. When the key is idle its job is queued and the worker
        (started if needed) runs it in FIFO order. While the key's job is
        running, further triggers only install their factory as the freshest
        pending and cancel the running job, whose worker then runs the
        successor; while it is merely queued, a trigger only refreshes the
        pending factory. Nothing is evaluated twice at once, and every save's
        latest state is evaluated.
        """
        start = False
        with self._guard:
            if chapter_id in self._running:
                self._running[chapter_id].set()
                self._pending[chapter_id] = make_job
                return
            already_queued = chapter_id in self._pending
            self._pending[chapter_id] = make_job
            if not already_queued:
                self._queue.put(chapter_id)
            if not self._worker_alive:
                self._worker_alive = True
                start = True
        if start:
            start_thread(self._worker_loop)

    def _worker_loop(self) -> None:
        while True:
            with self._guard:
                if self._queue.empty():
                    self._worker_alive = False
                    return
                chapter_id = self._queue.get()
            self._run(chapter_id)

    def _run(self, chapter_id: str) -> None:
        with self._guard:
            factory = self._pending.pop(chapter_id, None)
            if factory is None:
                return
            cancel = threading.Event()
            self._running[chapter_id] = cancel
        try:
            job = factory()
            job.cancel = cancel
            job.run()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Mention evaluation failed for chapter %s", chapter_id)
        finally:
            with self._guard:
                self._running.pop(chapter_id, None)
                if chapter_id in self._pending:
                    self._queue.put(chapter_id)
