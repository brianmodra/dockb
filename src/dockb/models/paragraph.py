from __future__ import annotations

from pydantic import Field

from dockb.models.sentence import Sentence

from .base import DockbModel


class Paragraph(DockbModel):
    sentences: list[Sentence] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.sentences:
            return self.text
        return "".join(sentence.getText() for sentence in self.sentences)

    def set_text(self, text: str, delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text
        if delay_semantics:
            return
