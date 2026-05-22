"""Synchronous sentence reconstruction."""

from dockb.models.base import DockbModel

from .sentence_reconstructor import SentenceReconstructor


class SyncSentenceReconstructor(SentenceReconstructor):  # pylint: disable=too-few-public-methods
    """Reconstructs sentences synchronously using the doc cache."""

    def run(self, model: DockbModel) -> None:
        if not hasattr(model, "tokens"):
            return
        model.tokenize(self.doc_cache)
