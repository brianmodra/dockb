"""Paragraph model for document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.sentence import Sentence

from .base import DockbModel


class Paragraph(DockbModel):
    """A paragraph containing a list of sentences."""

    sentences: list[Sentence] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.sentences:
            return self.text
        return "".join(sentence.get_text() for sentence in self.sentences)

    def set_text(self, text: str, _delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text

    def clear_semantics(self) -> None:
        for sentence in self.sentences:
            sentence.clear_semantics()
        self.sentences.clear()
