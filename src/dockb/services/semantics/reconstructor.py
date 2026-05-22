"""Abstract base class for document reconstruction."""

from abc import ABC, abstractmethod

from dockb.models.base import DockbModel
from dockb.models.utils.doc_cache import DocCache


class Reconstructor(ABC):  # pylint: disable=too-few-public-methods
    """Base class for reconstructing semantic model text."""

    def __init__(self, doc_cache: DocCache):
        self.doc_cache = doc_cache

    @abstractmethod
    def run(self, model: DockbModel) -> None:
        """Run reconstruction on the given model."""
