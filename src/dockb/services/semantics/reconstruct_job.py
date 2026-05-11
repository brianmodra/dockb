from __future__ import annotations

from typing import Any, Awaitable

from .job import Job


class ReconstructJob(Job):
    def __init__(
        self,
        model_id: str,
    ) -> None:
        super().__init__()
        self.model_id: str = model_id

    async def run(self) -> None:
        """does nothing yet"""
        pass