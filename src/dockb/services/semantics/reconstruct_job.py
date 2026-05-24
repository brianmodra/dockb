"""Job for reconstructing sentence semantics."""

from dockb.models.base import DockbModel
from dockb.services.semantics.doc_cache import DocCache

from .job import Job
from .sentence_tokenizer import SentenceTokenizer


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
        self._tokenizer: SentenceTokenizer | None = None

    def on_cancel(self) -> None:
        """Interrupt the tokenizer if it is currently running."""
        if self._tokenizer is not None:
            self._tokenizer.cancel()

    def run(self) -> None:
        """Run tokenization on the attached model if dirty."""
        if self.model is None or self.doc_cache is None:
            return
        if not self.model.dirty:
            return
        if hasattr(self.model, "tokens"):
            self._tokenizer = SentenceTokenizer()
            try:
                self.model.tokens = self._tokenizer.tokenize(self.model.get_text(), self.doc_cache)
                self.model.dirty = False
            finally:
                self._tokenizer = None
        self.model = None

    def set(self, sentence: DockbModel, doc_cache: DocCache) -> None:
        """Attach the sentence and doc cache for processing."""
        self.model = sentence
        self.doc_cache = doc_cache
