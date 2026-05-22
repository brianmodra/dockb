"""Job abstraction for async semantic processing tasks."""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """Lifecycle states for a processing job."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Job(ABC):
    """Abstract base class for async jobs executed by the JobQueue."""

    def __init__(self) -> None:
        self.timeout: int = 5000  # 5 seconds by default
        self.status: JobStatus = JobStatus.QUEUED
        self.result: Any = None
        self.error: Exception | None = None
        self.worker_task: asyncio.Task[Any] | None = None
        self.id: str = str(uuid.uuid4())

    def cancel(self) -> None:
        """Cancel the job and its underlying asyncio task."""
        self.status = JobStatus.CANCELLED
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()

    @abstractmethod
    async def run(self) -> None:
        """Implement the actual job logic here."""

    async def execute(self) -> None:
        """Run the job with a timeout, handling cancellation and errors."""
        self.status = JobStatus.RUNNING
        try:
            await asyncio.wait_for(self.run(), timeout=self.timeout)
            if self.status != JobStatus.CANCELLED:
                self.status = JobStatus.DONE
        except asyncio.CancelledError:
            self.status = JobStatus.CANCELLED
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.error = e
            self.status = JobStatus.FAILED
