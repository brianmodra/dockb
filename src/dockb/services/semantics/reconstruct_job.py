"""Job for hydrating and reconstructing model semantics."""

from dockb.models.base import DockbModel
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.semantics.chapter_hydrator import ChapterHydrator
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.document_hydrator import DocumentHydrator
from dockb.services.semantics.paragraph_hydrator import ParagraphHydrator
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer

from .job import Job


class ReconstructJob(Job):
    """Hydrates or tokenizes a model depending on its type."""

    def __init__(self) -> None:
        super().__init__()
        self.model_id: str = ""
        self.model: DockbModel | None = None
        self.doc_cache: DocCache | None = None
        self._tokenizer: SentenceTokenizer | None = None

    def on_cancel(self) -> None:
        """Interrupt the tokenizer if it is currently running."""
        if self._tokenizer is not None:
            self._tokenizer.cancel()

    def run(self) -> None:  # noqa: C901
        """Run hydration or tokenization on the attached model if dirty."""
        if self.model is None or self.doc_cache is None:
            return
        if not self.model.dirty:
            self.model = None
            return

        if isinstance(self.model, Document):
            DocumentHydrator().hydrate(self.model)
        elif isinstance(self.model, Chapter):
            ChapterHydrator().hydrate(self.model)
        elif isinstance(self.model, Paragraph):
            ParagraphHydrator(nlp=self.doc_cache.nlp).hydrate(self.model)
        elif isinstance(self.model, Sentence):
            self._tokenizer = SentenceTokenizer()
            try:
                self.model.tokens = self._tokenizer.tokenize(self.model.get_text(), self.doc_cache)
                self.model.dirty = False
            finally:
                self._tokenizer = None
        self.model = None

    def set(self, model: DockbModel, doc_cache: DocCache) -> None:
        """Attach the model and doc cache for processing."""
        self.model = model
        self.doc_cache = doc_cache
        self.model_id = model.id
