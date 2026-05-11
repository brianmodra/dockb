from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional
from abc import ABC, abstractmethod

import asyncio


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Job(ABC):
    def __init__(self) -> None:
        self.timeout: int = 5000  # 5 seconds by default
        self.status: JobStatus = JobStatus.QUEUED
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.worker_task: Optional[asyncio.Task[Any]] = None
        self.id: str = str(uuid.uuid4())

    def cancel(self) -> None:
        self.status = JobStatus.CANCELLED
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()

    @abstractmethod
    async def run(self) -> None:
        pass

    async def execute(self) -> None:
        self.status = JobStatus.RUNNING
        try:
            await asyncio.wait_for(self.run(), timeout=self.timeout)
            if self.status != JobStatus.CANCELLED:
                self.status = JobStatus.DONE
        except asyncio.CancelledError:
            self.status = JobStatus.CANCELLED
        except Exception as e:
            self.error = e
            self.status = JobStatus.FAILED
