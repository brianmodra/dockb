from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable

if TYPE_CHECKING:
    from dockb.models import Sentence

from .job import Job


class DeleteJob(Job):
    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.sentence = None

    async def run(self) -> None:
        if self.sentence == None:
            return
        if not self.sentence.dirty:
            return
        self.sentence.tokens.clear()
        self.sentence = None

    def set(self, sentence: Sentence):
        self.sentence = sentence
