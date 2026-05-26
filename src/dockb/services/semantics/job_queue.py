"""Thread-safe job queue for semantic processing tasks."""

import logging
import queue
import threading
from typing import Final

from .job import Job, JobStatus
from .reconstruct_job import ReconstructJob
from .sentence_tokenizer import TokenizationCancelled

WORKER_GET_TIMEOUT: Final = 1.0
logger = logging.getLogger(__name__)
QUEUE_THREAD_JOIN_TIMEOUT: Final = 300.0


class JobQueue:  # pylint: disable=too-many-instance-attributes
    """Thread-safe queue that manages and executes semantic processing jobs."""

    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._reconstruct_jobs: dict[str, ReconstructJob] = {}
        self._worker_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._jobs: dict[str, Job] = {}
        self._started_event = threading.Event()
        self._completed_event = threading.Event()
        self._pending_count: int = 0
        self._lock = threading.Lock()

    @property
    def reconstruct_jobs(self) -> dict[str, ReconstructJob]:
        """Return a read-only view of pending reconstruct jobs."""
        with self._lock:
            return dict(self._reconstruct_jobs)

    @property
    def pending_count(self) -> int:
        """read-only copy of _pending_count"""
        return self._pending_count

    def enqueue(self, job: Job) -> None:
        """Add a job to the queue for execution."""
        with self._lock:
            self._completed_event.clear()
            self._jobs[job.id] = job
            self._pending_count += 1
            if isinstance(job, ReconstructJob):
                if job.model_id in self._reconstruct_jobs:
                    old_job = self._reconstruct_jobs[job.model_id]
                    old_job.cancel()
                self._reconstruct_jobs[job.model_id] = job
        self._queue.put_nowait(job.id)

    def cancel_job(self, job: Job) -> bool:
        """Cancel a queued job."""
        with self._lock:
            if job.id not in self._jobs:
                return False
            job.cancel()
            return True

    def is_running(self) -> bool:
        """Return True if the worker is active and not shutting down."""
        return self._worker_thread is not None and not self._shutdown_event.is_set()

    def start(self) -> None:
        """Start the background worker thread. Safe to call multiple times."""
        if self._shutdown_event.is_set():
            self._shutdown_event.clear()
        if self._worker_thread is not None:
            return
        self._completed_event.clear()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

    def shutdown(self, timeout: float = QUEUE_THREAD_JOIN_TIMEOUT) -> None:
        """Stop the worker and wait for it to finish."""
        self._shutdown_event.set()
        with self._lock:
            thread = self._worker_thread
            self._worker_thread = None
        if thread is not None and thread.is_alive():
            logger.debug("waiting %f seconds for _worker_thread", timeout)
            thread.join(timeout=timeout)
        # reset everything:
        with self._lock:
            self._shutdown_event.clear()
            self._reconstruct_jobs.clear()
            self._jobs.clear()
            self._started_event.clear()
            self._completed_event.clear()
            self._pending_count = 0

    def join(self, timeout: float = QUEUE_THREAD_JOIN_TIMEOUT) -> None:
        """Wait until all queued jobs are completed.

        Note: returns a point-in-time snapshot. A new job enqueued between
        this call returning and the caller acting on it will not be waited on.
        """
        if self._shutdown_event.is_set():
            return
        self._started_event.wait()
        queue_status = "empty" if self._queue.empty() else "waiting"
        logger.debug("queue %s, jobs: %d, pending %d", queue_status, len(self._jobs), self._pending_count)
        self._completed_event.wait(timeout=timeout)

    def _worker(self) -> None:
        logger.debug("starting _worker")
        self._started_event.set()
        while not self._shutdown_event.is_set():
            try:
                job_id = self._queue.get(timeout=WORKER_GET_TIMEOUT)
                logger.debug("got job id %s", job_id)
            except queue.Empty:
                logger.debug("queue is empty")
                with self._lock:
                    if self._pending_count == 0:
                        self._completed_event.set()
                continue

            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status == JobStatus.CANCELLED:
                    if job is not None:
                        job.done.set()  # Its not done as in status==DONE, but it is done-with
                    self._pending_count -= 1
                    self._queue.task_done()
                    logger.debug("job %s was cancelled", job_id)
                    continue

                job.status = JobStatus.RUNNING

            timer = threading.Timer(job.timeout, job.cancel)
            timer.daemon = True
            timer.start()

            try:
                logger.debug("executing job %s", job_id)
                job.run()
                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.DONE
            except (KeyboardInterrupt, SystemExit):
                logger.exception("system exit for job %s", job_id)
                raise
            except TokenizationCancelled as exc:
                logger.debug("job %s cancelled during tokenization", job_id)
                job.error = exc
                job.status = JobStatus.CANCELLED
            except Exception as exc:  # pylint: disable=broad-exception-caught
                job.error = exc
                job.status = JobStatus.FAILED
            finally:
                timer.cancel()
                job.done.set()

            with self._lock:
                self._pending_count -= 1
                self._queue.task_done()
                if self._jobs.get(job_id) == job:
                    del self._jobs[job_id]
                    if isinstance(job, ReconstructJob):
                        if self._reconstruct_jobs.get(job.model_id) is job:
                            del self._reconstruct_jobs[job.model_id]

    def list_jobs(self) -> list[str]:
        """Return IDs of all currently queued jobs."""
        with self._lock:
            return [job_id for job_id, job in self._jobs.items() if job.status == JobStatus.QUEUED]
