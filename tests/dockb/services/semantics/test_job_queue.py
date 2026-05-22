

import asyncio

import pytest

from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.job import Job, JobStatus
from dockb.services.semantics.job_queue import JobQueue
from dockb.services.semantics.reconstruct_job import ReconstructJob


class SimpleJob(Job):
    count: int = 0

    def __init__(self) -> None:
        super().__init__()
        self.done = asyncio.Event()
        self.ready_to_start = asyncio.Event()
        self.almost_done = asyncio.Event()
        self.started = asyncio.Event()
        SimpleJob.count += 1
        self.seq = 0

    def set_ready_to_start(self) -> None:
        self.ready_to_start.set()

    def set_almost_done(self) -> None:
        self.almost_done.set()

    async def run(self) -> None:
        self.started.set()
        await self.ready_to_start.wait()
        self.seq = SimpleJob.count
        await self.almost_done.wait()


@pytest.mark.asyncio
async def test_job_queue_runs():
    queue = JobQueue()
    await queue.start()
    assert await queue.is_running()
    await queue.shutdown()
    assert not await queue.is_running()


@pytest.mark.asyncio
async def test_job_queue_queues_jobs_and_runs_them_in_order():
    queue = JobQueue()
    assert not await queue.is_running()
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
    await queue.start()
    await job1.started.wait()
    assert job1.status == JobStatus.RUNNING
    assert job2.status == JobStatus.QUEUED
    job1.set_ready_to_start()
    job1.set_almost_done()
    await job1.done.wait()
    await job2.started.wait()
    assert job2.status == JobStatus.RUNNING
    job2.set_ready_to_start()
    job2.set_almost_done()
    await job2.done.wait()
    assert job1.status == JobStatus.DONE
    assert job2.status == JobStatus.DONE
    await queue.join()
    jobs = queue.list_jobs()
    assert len(jobs) == 0
    await queue.shutdown()


@pytest.mark.asyncio
async def test_job_queue_can_cancel_jobs_that_are_running_and_lets_other_jobs_be_run_afterwards():
    queue = JobQueue()
    assert not await queue.is_running()
    job_to_cancel = SimpleJob()
    seq_to_cancel = job_to_cancel.seq
    job_to_remain = SimpleJob()
    queue.enqueue(job_to_cancel)
    job_to_remain = SimpleJob()
    queue.enqueue(job_to_remain)
    assert job_to_cancel.status == JobStatus.QUEUED
    assert job_to_remain.status == JobStatus.QUEUED
    await queue.start()
    await job_to_cancel.started.wait()
    assert job_to_cancel.status == JobStatus.RUNNING
    queue.cancel_job(job_to_cancel)
    assert job_to_cancel.status == JobStatus.CANCELLED
    # seq should be zero if the test has not run
    assert job_to_cancel.seq == 0
    await job_to_remain.started.wait()
    assert job_to_remain.status == JobStatus.RUNNING
    job_to_remain.set_ready_to_start()
    job_to_remain.set_almost_done()
    await job_to_remain.done.wait()
    assert job_to_remain.status == JobStatus.DONE
    await queue.join()
    jobs = queue.list_jobs()
    assert len(jobs) == 0
    await queue.shutdown()


@pytest.mark.asyncio
async def test_job_queue_stores_reconstruct_jobs_into_dict_but_not_delete_jobs():
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


@pytest.mark.asyncio
async def test_job_queue_removes_reconstruct_jobs_for_same_model_but_leaves_delete_jobs():
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
