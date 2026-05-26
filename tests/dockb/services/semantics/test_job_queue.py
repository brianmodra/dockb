import threading

from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.job import Job, JobStatus
from dockb.services.semantics.job_queue import JobQueue
from dockb.services.semantics.reconstruct_job import ReconstructJob

STRESS_NUM_THREADS = 10
STRESS_JOBS_PER_THREAD = 20


class SimpleJob(Job):
    count: int = 0

    def __init__(self) -> None:
        super().__init__()
        self.done = threading.Event()
        self.ready_to_start = threading.Event()
        self.almost_done = threading.Event()
        self.started = threading.Event()
        SimpleJob.count += 1
        self.seq = 0

    def set_ready_to_start(self) -> None:
        self.ready_to_start.set()

    def set_almost_done(self) -> None:
        self.almost_done.set()

    def on_cancel(self) -> None:
        """Cancel the job. signal the events to stop it from waiting."""
        self.set_ready_to_start()
        self.set_almost_done()

    def run(self) -> None:
        self.started.set()
        self.ready_to_start.wait()
        self.seq = SimpleJob.count
        self.almost_done.wait()


class FastJob(Job):
    """A job that runs to completion without manual signaling."""

    run_order: list[str] = []
    _order_lock = threading.Lock()

    def __init__(self) -> None:
        super().__init__()
        self.done = threading.Event()
        self.started = threading.Event()

    def run(self) -> None:
        self.started.set()
        with FastJob._order_lock:
            FastJob.run_order.append(self.id)
        self.done.set()


class FailingJob(Job):
    def __init__(self, exc: type[Exception] | None = None) -> None:
        super().__init__()
        self.exc = exc
        self.started = threading.Event()

    def run(self) -> None:
        self.started.set()
        if self.exc is not None:
            raise self.exc()


def test_job_queue_runs():
    queue = JobQueue()
    queue.start()
    assert queue.is_running()
    queue.shutdown()
    assert not queue.is_running()


def test_job_queue_cancel_job_returns_false_for_unknown_job():
    queue = JobQueue()
    queue.start()
    job = SimpleJob()
    result = queue.cancel_job(job)
    assert result is False
    queue.shutdown()


def test_job_queue_queues_jobs_and_runs_them_in_order():
    queue = JobQueue()
    assert not queue.is_running()
    job1 = SimpleJob()
    id1 = job1.id
    job2 = SimpleJob()
    id2 = job2.id
    queue.enqueue(job1)
    assert job1.status == JobStatus.QUEUED
    queue.enqueue(job2)
    assert job2.status == JobStatus.QUEUED
    jobs = queue.list_jobs()
    assert len(jobs) == 2
    assert jobs[0] == id1
    assert jobs[1] == id2
    queue.start()
    job1.started.wait()
    assert job1.status == JobStatus.RUNNING
    assert job2.status == JobStatus.QUEUED
    job1.set_ready_to_start()
    job1.set_almost_done()
    job1.done.wait()
    job2.started.wait()
    assert job2.status == JobStatus.RUNNING
    job2.set_ready_to_start()
    job2.set_almost_done()
    job2.done.wait()
    assert job1.status == JobStatus.DONE
    assert job2.status == JobStatus.DONE
    queue.join()
    jobs = queue.list_jobs()
    assert len(jobs) == 0
    queue.shutdown()


def test_job_queue_can_cancel_jobs_that_are_running_and_lets_other_jobs_be_run_afterwards():
    queue = JobQueue()
    assert not queue.is_running()
    job_to_cancel = SimpleJob()
    queue.enqueue(job_to_cancel)
    job_to_remain = SimpleJob()
    queue.enqueue(job_to_remain)
    assert job_to_cancel.status == JobStatus.QUEUED
    assert job_to_remain.status == JobStatus.QUEUED
    queue.start()
    job_to_cancel.started.wait()
    assert job_to_cancel.status == JobStatus.RUNNING
    job_to_cancel.set_ready_to_start()
    queue.cancel_job(job_to_cancel)
    assert job_to_cancel.status == JobStatus.CANCELLED
    job_to_remain.started.wait()
    assert job_to_remain.status == JobStatus.RUNNING
    job_to_remain.set_ready_to_start()
    job_to_remain.set_almost_done()
    job_to_remain.done.wait()

    # job_to_cancel status should still be CANCELLED
    assert job_to_cancel.status == JobStatus.CANCELLED
    assert job_to_remain.status == JobStatus.DONE
    queue.join()
    jobs = queue.list_jobs()
    assert len(jobs) == 0
    queue.shutdown()


def test_job_queue_stores_reconstruct_jobs_into_dict_but_not_delete_jobs():
    queue = JobQueue()
    job1 = DeleteJob()
    job2 = ReconstructJob("model2")
    job3 = ReconstructJob("model3")
    queue.enqueue(job1)
    queue.enqueue(job2)
    queue.enqueue(job3)
    assert queue.reconstruct_jobs["model2"] == job2
    assert queue.reconstruct_jobs["model3"] == job3
    jobs = queue.list_jobs()
    assert len(jobs) == 3
    assert len(queue.reconstruct_jobs) == 2


def test_job_queue_removes_reconstruct_jobs_for_same_model_but_leaves_delete_jobs():
    queue = JobQueue()
    job1 = DeleteJob()
    job2 = ReconstructJob("model2")
    job3 = ReconstructJob("same-model")
    id3 = job3.id
    queue.enqueue(job1)
    queue.enqueue(job2)
    queue.enqueue(job3)
    job4 = ReconstructJob("same-model")
    queue.enqueue(job4)
    job5 = DeleteJob()
    queue.enqueue(job5)
    assert job3.status == JobStatus.CANCELLED
    assert queue.reconstruct_jobs["same-model"] == job4
    jobs = queue.list_jobs()
    assert id3 not in jobs


def test_job_queue_auto_cancels_job_on_timeout():
    queue = JobQueue()
    queue.start()
    job = SimpleJob()
    job.timeout = 0.1  # 100ms timeout
    queue.enqueue(job)
    job.started.wait()
    assert job.status == JobStatus.RUNNING
    job.done.wait()
    assert job.status == JobStatus.CANCELLED
    queue.shutdown()


def test_job_queue_crashes_on_keyboard_interrupt():
    queue = JobQueue()
    captured = []
    original_hook = threading.excepthook
    threading.excepthook = lambda args: (
        captured.append(args.exc_value) if isinstance(args.exc_value, KeyboardInterrupt) else original_hook(args)
    )
    try:
        queue.start()
        job = FailingJob(exc=KeyboardInterrupt)
        queue.enqueue(job)
        job.started.wait()
        job.done.wait()
        assert job.status == JobStatus.RUNNING
        queue._worker_thread.join(timeout=5.0)
        assert not queue._worker_thread.is_alive()
        assert any(isinstance(e, KeyboardInterrupt) for e in captured)
    finally:
        threading.excepthook = original_hook


def test_job_queue_handles_value_error_without_crashing():
    queue = JobQueue()
    queue.start()
    failing_job = FailingJob(exc=ValueError)
    ok_job = SimpleJob()
    queue.enqueue(failing_job)
    queue.enqueue(ok_job)
    failing_job.started.wait()
    failing_job.done.wait()
    assert failing_job.status == JobStatus.FAILED
    assert isinstance(failing_job.error, ValueError)
    ok_job.started.wait()
    assert ok_job.status == JobStatus.RUNNING
    ok_job.set_ready_to_start()
    ok_job.set_almost_done()
    ok_job.done.wait()
    assert ok_job.status == JobStatus.DONE
    queue.shutdown()


def test_job_queue_start_is_idempotent():
    queue = JobQueue()
    queue.start()
    first_thread = queue._worker_thread
    assert queue.is_running()
    queue.start()
    assert queue._worker_thread is first_thread
    assert queue.is_running()
    queue.start()
    assert queue._worker_thread is first_thread
    assert queue.is_running()
    queue.shutdown()
    assert not queue.is_running()


def test_job_queue_shutdown_is_idempotent():
    queue = JobQueue()
    queue.start()
    assert queue.is_running()
    queue.shutdown()
    assert not queue.is_running()
    queue.shutdown()
    queue.shutdown()


class StressEnqueuer(threading.Thread):
    def __init__(self, queue: JobQueue, result: list[str], barrier: threading.Barrier) -> None:
        super().__init__()
        self.queue = queue
        self.result = result
        self.barrier = barrier

    def run(self) -> None:
        self.barrier.wait()
        for _ in range(STRESS_JOBS_PER_THREAD):
            job = FastJob()
            self.result.append(job.id)
            self.queue.enqueue(job)


def test_job_queue_stress_test_multi_threaded_ordering():
    queue = JobQueue()
    queue.start()

    FastJob.run_order.clear()

    results: list[list[str]] = [[] for _ in range(STRESS_NUM_THREADS)]
    threads: list[StressEnqueuer] = []
    barrier = threading.Barrier(STRESS_NUM_THREADS)

    for i in range(STRESS_NUM_THREADS):
        thread = StressEnqueuer(queue, results[i], barrier)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    expected_count = STRESS_NUM_THREADS * STRESS_JOBS_PER_THREAD
    expected_ids = {jid for ids in results for jid in ids}

    queue.join(timeout=60.0)

    assert len(FastJob.run_order) == expected_count
    assert set(FastJob.run_order) == expected_ids

    for ids in results:
        indices = [FastJob.run_order.index(jid) for jid in ids]
        assert indices == sorted(indices)

    queue.shutdown()


def test_reconstruct_job_cancels_tokenization():
    from dockb.services.semantics.sentence_tokenizer import (
        SentenceTokenizer,
    )

    slow_tok = SentenceTokenizer()
    slow_tok.cancel()
    assert slow_tok._cancel_event.is_set()


def test_reconstruct_job_cancels_tokenization_via_queue():
    from unittest.mock import patch

    from dockb.models.sentence import Sentence
    from dockb.services.semantics.sentence_tokenizer import (
        SentenceTokenizer,
        TokenizationCancelled,
    )

    blocked = threading.Event()
    tokenizer_started = threading.Event()

    class BlockingTokenizer(SentenceTokenizer):
        def tokenize(self, text, doc_cache):
            tokenizer_started.set()
            blocked.wait()
            if self._cancel_event.is_set():
                raise TokenizationCancelled()
            return []

    sentence = Sentence(text="hello world")
    sentence.dirty = True

    with patch.object(SentenceTokenizer, "__new__", return_value=BlockingTokenizer()):
        queue = JobQueue()
        queue.start()
        job = ReconstructJob("model-1")
        job.set(sentence, doc_cache=None)
        job.doc_cache = "ignored"

        queue.enqueue(job)
        tokenizer_started.wait()
        queue.cancel_job(job)
        blocked.set()

        job.done.wait(timeout=5.0)
        assert job.status == JobStatus.CANCELLED
        queue.shutdown()
