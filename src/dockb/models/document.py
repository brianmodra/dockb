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


    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        """
        Replace the text inclusively

        start : int
                zero-based offset of the start of the text to be replaced
        end   : int
                zero-based offset of the last character to be replaced
        test  : str
                the replacement string of text

        E.g. if it starts with "Hello World!", and this function is called with start=6 and end=10, and text="Sir"
        Then the text in the document will become "Hello Sir!".

        If the existing text is empty, you can't replace it. In that case, use append_text
        """
        self.dirty = True


    def apply_append_text(self, text: str) -> None:
        """
        Appends the text after the end of the existing text
        """
        self.text = self.text + text
        self.dirty = True

