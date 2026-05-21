from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from .delete_job import DeleteJob
from .job import Job, JobStatus
from .reconstruct_job import ReconstructJob


class JobQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.reconstruct_jobs: Dict[str, ReconstructJob] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._jobs: Dict[str, Job] = {}
        self._completed_event: asyncio.Event = asyncio.Event()
        self._new_job_event: asyncio.Event = asyncio.Event()
        self._pending_count: int = 0

    def enqueue(self, job: Job) -> None:
        self._jobs[job.id] = job
        self.queue.put_nowait(job.id)
        self._pending_count += 1
        self._new_job_event.set()
        if isinstance(job, ReconstructJob):
            if job.model_id in self.reconstruct_jobs:
                old_job = self.reconstruct_jobs[job.model_id]
                old_job.cancel()
                self._jobs.pop(old_job.id, None)
                self._pending_count -= 1
            self.reconstruct_jobs[job.model_id] = job

    def cancel_job(self, job: Job) -> bool:
        if job.id not in self._jobs:
            return False
        job.cancel()
        self._jobs.pop(job.id, None)
        return True

    async def start(self) -> None:
        if self._worker_task is None:
            self._completed_event.clear()
            self._worker_task = asyncio.create_task(self._worker())

    async def is_running(self) -> bool:
        return self._worker_task is not None and not self._shutdown

    async def shutdown(self) -> None:
        self._shutdown = True
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def join(self) -> None:
        await self._completed_event.wait()

    async def _worker(self) -> None:
        while not self._shutdown:
            if self.queue.empty() and self._pending_count == 0:
                self._completed_event.set()
                break

            try:
                job_id = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                await self._new_job_event.wait()
                self._new_job_event.clear()
                continue

            job = self._jobs.get(job_id)
            if job is None or job.status == JobStatus.CANCELLED:
                self._pending_count -= 1
                self.queue.task_done()
                continue

            job.status = JobStatus.RUNNING
            job.worker_task = asyncio.current_task()

            try:
                await job.execute()
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
            except Exception:
                pass
            finally:
                if hasattr(job, 'done'):
                    job.done.set()

            self._pending_count -= 1
            self.queue.task_done()

            if self._jobs.get(job_id) == job:
                self._jobs.pop(job_id, None)
                if isinstance(job, ReconstructJob):
                    self.reconstruct_jobs.pop(job.model_id, None)

    def list_jobs(self) -> List[str]:
        return [job_id for job_id in list(self._jobs.keys()) if self._jobs[job_id].status == JobStatus.QUEUED]