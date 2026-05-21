from abc import ABC, abstractmethod

from dockb.models.base import DockbModel
from dockb.models.utils import DocCache


class Reconstructor(ABC):
    def __init__(self, doc_cache: DocCache):
        self.doc_cache = doc_cache

    @abstractmethod
    def run(self, model: DockbModel):
        pass