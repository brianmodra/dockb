from typing import TYPE_CHECKING

from dockb.models.base import DockbModel
from dockb.models.utils.doc_cache import DocCache

from .sentence_reconstructor import SentenceReconstructor

if TYPE_CHECKING:
    from dockb.models.sentence import Sentence


class SyncSentenceReconstructor(SentenceReconstructor):
    def __init__(self, doc_cache: DocCache):
        super().__init__(doc_cache)

    def run(self, model: DockbModel):
        sentence: Sentence = model
        sentence.tokenize(self.doc_cache)