"""Paragraph model for document hierarchy."""

from __future__ import annotations

from pydantic import Field, PrivateAttr, model_validator

from dockb.models.formatting import FormatRun, LayoutKind, LayoutVariant, validate_layout
from dockb.models.sentence import Sentence
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Paragraph(DockbModel):
    """A paragraph containing a list of sentences."""

    sentences: DockbCollection[Sentence] = Field(default_factory=DockbCollection)
    layout_kind: LayoutKind = "normal"
    layout_variant: LayoutVariant = ""
    _format_runs: list[FormatRun] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def layout_is_consistent(self) -> Paragraph:
        """Require a variant exactly when the paragraph is quoted."""
        validate_layout(self.layout_kind, self.layout_variant)
        return self

    @property
    def format_runs(self) -> list[FormatRun]:
        """Transient formatting runs, consumed when sentences are hydrated."""
        return self._format_runs

    @format_runs.setter
    def format_runs(self, value: list[FormatRun]) -> None:
        self._format_runs = value

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
