from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable

if TYPE_CHECKING:
    from dockb.models import Sentence
    from dockb.models.utils import DocCache

from .job import Job


class ReconstructJob(Job):
    def __init__(
        self,
        model_id: str,
    ) -> None:
        super().__init__()
        self.model_id: str = model_id
        self.sentence = None

    async def run(self) -> None:
        if self.sentence == None:
            return
        if not self.sentence.dirty:
            return
        self.sentence.tokenize(self.doc_cache)
        self.sentence = None

    def set(self, sentence: Sentence, doc_cache: DocCache):
        self.sentence = sentence
        self.d0c_cache = doc_cache