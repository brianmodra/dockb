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
        self.model: DockbModel | None = None
        self.doc_cache: DocCache | None = None

    async def run(self) -> None:
        """Run tokenization on the attached model if dirty."""
        if self.model is None or self.doc_cache is None:
            return
        if not self.model.dirty:
            return
        self.model.tokenize(self.doc_cache)
        self.model = None

    def set(self, sentence: DockbModel, doc_cache: DocCache) -> None:
        """Attach the sentence and doc cache for processing."""
        self.model = sentence
        self.doc_cache = doc_cache
