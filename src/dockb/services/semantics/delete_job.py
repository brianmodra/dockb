# pylint: disable=cyclic-import
"""Job for clearing sentence tokens before reconstruction."""

from __future__ import annotations

from dockb.models.base import DockbModel

from .job import Job


class DeleteJob(Job):
    """Clears existing tokens from a sentence before new tokenization."""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.sentence: DockbModel | None = None

    async def run(self) -> None:
        if self.sentence is None:
            return
        if not self.sentence.dirty:
            return
        self.sentence.clear_semantics()
        self.sentence = None

    def set(self, sentence: DockbModel) -> None:
        """Attach the sentence to be cleared."""
        self.sentence = sentence
