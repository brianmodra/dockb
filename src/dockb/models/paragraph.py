from __future__ import annotations
from pydantic import Field
from .base import DockbModel
from dockb.models.sentence import Sentence


class Paragraph(DockbModel):
    sentences: list[Sentence] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        self.text = text
