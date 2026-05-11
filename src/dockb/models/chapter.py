from __future__ import annotations
from .base import DockbModel
from pydantic import Field
from dockb.models.paragraph import Paragraph

class Chapter(DockbModel):
    paragraphs: list[Paragraph] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        self.text = text
