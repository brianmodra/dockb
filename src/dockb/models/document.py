from __future__ import annotations

import uuid

from mypy.plugins.proper_plugin import proper_type_hook
from pydantic import Field, PositiveInt

from .base import DockbModel
from dockb.models.chapter import Chapter

class Document(DockbModel):
    id: str = uuid.uuid4()
    chapters: list[Chapter] = Field(default_factory=list)
    text: str = ""
    dirty: bool = False


    @property
    def id(self) -> str:
        return self.id

    @property
    def dirty(self) -> bool:
        return self.dirty

    @property
    def test(self) -> str:
        return self.str

    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        self.dirty = True
