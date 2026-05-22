"""Abstract base class for sentence-level reconstruction."""

from abc import ABC, abstractmethod

from dockb.models.base import DockbModel

from .reconstructor import Reconstructor


class SentenceReconstructor(Reconstructor, ABC):  # pylint: disable=too-few-public-methods
    """Base class for sentence reconstruction with doc caching."""

    @abstractmethod
    def run(self, model: DockbModel) -> None:
        """Run sentence reconstruction on the given model."""
