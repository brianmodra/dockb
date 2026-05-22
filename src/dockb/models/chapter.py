"""Chapter model for document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.paragraph import Paragraph

from .base import DockbModel


class Chapter(DockbModel):
    """A chapter containing a list of paragraphs."""

    paragraphs: list[Paragraph] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.paragraphs:
            return self.text
        return "".join(paragraph.get_text() for paragraph in self.paragraphs)

    def set_text(self, text: str, _delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text

    def clear_semantics(self) -> None:
        for paragraph in self.paragraphs:
            paragraph.clear_semantics()
        self.paragraphs.clear()
