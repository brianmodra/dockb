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
        self.model: DockbModel | None = None

    def run(self) -> None:
        """Clear semantics on the attached model if dirty."""
        if self.model is None:
            return
        if not self.model.dirty:
            return
        self.model.clear_semantics()
        self.model = None

    def set(self, sentence: DockbModel) -> None:
        """Attach the sentence to be cleared."""
        self.model = sentence
