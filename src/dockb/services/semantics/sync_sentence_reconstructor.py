"""Synchronous sentence reconstruction."""

from dockb.models.base import DockbModel
from dockb.services.semantics.sentence_reconstructor import SentenceReconstructor
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer


class SyncSentenceReconstructor(SentenceReconstructor):  # pylint: disable=too-few-public-methods
    """Reconstructs sentences synchronously using the doc cache."""

    def run(self, model: DockbModel) -> None:
        if not hasattr(model, "tokens"):
            return
        tokenizer = SentenceTokenizer()
        model.tokens = tokenizer.tokenize(model.get_text(), self.doc_cache)
        model.dirty = False
