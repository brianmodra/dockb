from __future__ import annotations

from pydantic import Field

from dockb.models.paragraph import Paragraph

from .base import DockbModel


class Chapter(DockbModel):
    paragraphs: list[Paragraph] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.paragraphs:
            return self.text
        return "".join(paragraph.getText() for paragraph in self.paragraphs)

    def set_text(self, text: str, delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text
        if delay_semantics:
            return
