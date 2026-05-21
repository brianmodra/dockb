from abc import ABC, abstractmethod

from dockb.models.base import DockbModel
from dockb.models.utils import DocCache

from .reconstructor import Reconstructor


class SentenceReconstructor(Reconstructor, ABC):
    def __init__(self, doc_cache: DocCache):
        super().__init__(doc_cache)

    @abstractmethod
    def run(self, model: DockbModel):
        pass
