"""Paragraph model for document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Paragraph(DockbModel):
    """A paragraph containing a list of sentences."""

    sentences: DockbCollection[Sentence] = Field(default_factory=DockbCollection)

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.sentences:
            return self.text
        return "".join(sentence.get_text() for sentence in self.sentences)

    def clear_semantics(self) -> None:
        for sentence in self.sentences:
            sentence.clear_semantics()
        self.sentences.clear()

    def delete_child(self, child_id: str) -> bool:
        if self.sentences.delete(child_id):
            return True
        for sentence in self.sentences:
            if sentence.delete_child(child_id):
                return True
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        if not isinstance(child, Sentence):
            raise TypeError(f"Expected Sentence, got {type(child).__name__}")
        self.sentences.insert(child, insertion_mode, after)
