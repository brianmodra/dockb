"""Synchronous reconstruction via hydration or tokenization."""

from spacy.language import Language

from dockb.models.base import DockbModel
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.semantics.chapter_hydrator import ChapterHydrator
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.document_hydrator import DocumentHydrator
from dockb.services.semantics.paragraph_hydrator import ParagraphHydrator
from dockb.services.semantics.reconstructor import Reconstructor
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer


class SyncReconstructor(Reconstructor):  # pylint: disable=too-few-public-methods
    """Reconstructs models synchronously by hydrating or tokenizing based on type."""

    def __init__(self, doc_cache: DocCache, nlp: Language):
        super().__init__(doc_cache)
        self._nlp = nlp

    def run(self, model: DockbModel) -> None:
        """Run hydration or tokenization on the model based on its type."""
        if isinstance(model, Document):
            DocumentHydrator().hydrate(model)
        elif isinstance(model, Chapter):
            ChapterHydrator().hydrate(model)
        elif isinstance(model, Paragraph):
            ParagraphHydrator(nlp=self._nlp).hydrate(model)
        elif isinstance(model, Sentence):
            tokenizer = SentenceTokenizer()
            model.tokens[:] = tokenizer.tokenize(model.get_text(), self.doc_cache)
        model.dirty = False
