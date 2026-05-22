"""Job for reconstructing sentence semantics."""

from __future__ import annotations

from dockb.models.base import DockbModel
from dockb.models.utils.doc_cache import DocCache

from .job import Job


class ReconstructJob(Job):
    """Queues a sentence for tokenization and semantic reconstruction."""

    def __init__(
        self,
        model_id: str,
    ) -> None:
        super().__init__()
        self.model_id: str = model_id
        self.sentence: DockbModel | None = None
        self.doc_cache: DocCache | None = None

    async def run(self) -> None:
        if self.sentence is None or self.doc_cache is None:
            return
        if not self.sentence.dirty:
            return
        doc_cache: DocCache = self.doc_cache
        self.sentence.tokenize(doc_cache)
        self.sentence = None

    def set(self, sentence: DockbModel, doc_cache: DocCache) -> None:
        """Attach the sentence and doc cache for processing."""
        self.sentence = sentence
        self.doc_cache = doc_cache
