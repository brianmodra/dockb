"""Job abstraction for semantic processing tasks."""

import threading
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, final


class JobStatus(Enum):
    """Enumeration of job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Job(ABC):
    """Abstract base class for semantic processing jobs."""

    def __init__(self) -> None:
        self.timeout: float = 5.0  # seconds (informational only in sync mode)
        self.status: JobStatus = JobStatus.QUEUED
        self.result: Any = None
        self.error: Exception | None = None
        self.id: str = str(uuid.uuid4())
        self.done = threading.Event()

    @final
    def cancel(self) -> None:
        """Cancel the job. Note: Running threads cannot be forcefully cancelled."""
        if self.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return
        was_running = self.status == JobStatus.RUNNING
        self.status = JobStatus.CANCELLED
        if was_running:
            self.on_cancel()

    def on_cancel(self) -> None:  # noqa: B027
        """Execute whatever is needed to cancel a job that is already running."""

    @abstractmethod
    def run(self) -> None:
        """Execute the job's specific logic."""
