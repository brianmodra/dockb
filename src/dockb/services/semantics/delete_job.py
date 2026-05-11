from __future__ import annotations

from typing import Any, Awaitable

from .job import Job


class DeleteJob(Job):
    def __init__(
        self,
    ) -> None:
        super().__init__()

    async def run(self) -> None:
        """does nothing yet"""
        pass
