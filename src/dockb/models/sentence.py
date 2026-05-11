from __future__ import annotations
from pydantic import Field
from .base import DockbModel
from dockb.models.token import Token


class Sentence(DockbModel):
    tokens: list[Token] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        self.text = text
