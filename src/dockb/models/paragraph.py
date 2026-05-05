from __future__ import annotations

import uuid

from pydantic import Field

from .base import DockbModel
from dockb.models.sentence import Sentence


class Paragraph(DockbModel):
    id: str = uuid.uuid4()
    sentences: list[Sentence] = Field(default_factory=list)
    text: str = ""
    dirty: bool = False

    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        return

    def apply_append_text(self, text: str) -> None:
        return

    def apply_insert_text(self, pos: int, text: str) -> None:
        return
