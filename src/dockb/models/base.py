from __future__ import annotations

import uuid
from pydantic import BaseModel, ConfigDict, Field
from abc import ABC, abstractmethod
from dockb.exceptions import EditTextRangeError


class DockbModel(BaseModel, ABC):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dirty: bool = False
    model_config = ConfigDict(populate_by_name=True)

    @abstractmethod
    def get_text(self) -> str:
        pass

    @abstractmethod
    def set_text(self, text: str) -> None:
        pass

    def apply_edit_text(self, start: int, end: int, text: str) -> None:
        """
        Replace the text inclusively

        start : int
                zero-based offset of the start of the text to be replaced
        end   : int
                zero-based offset of the last character to be replaced
        text  : str
                the replacement string of text

        E.g. if it starts with "Hello World!", and this function is called with start=6 and end=10, and text="Sir"
        Then the text in the document will become "Hello Sir!".

        If the existing text is empty, you can't replace it. In that case, use apply_append_text
        """

        self_text = self.get_text()

        if end < start:
            raise EditTextRangeError("end is before start", start, end)
        if not self_text:
            raise EditTextRangeError("no text to edit", start, end)
        if start >= len(self_text) or start < 0:
            raise EditTextRangeError("start is out of range", start, end)
        if end >= len(self_text) or end < 0:
            raise EditTextRangeError("end is out of range", start, end)
        self.set_text(self_text[:start] + text + self_text[end + 1 :])
        self.dirty = True

    def apply_append_text(self, text: str) -> None:
        """
        Appends the text after the end of the existing text
        """

        if not text:
            return
        self_text = self.get_text()
        self.set_text(self_text + text)
        self.dirty = True

    def apply_insert_text(self, pos: int, text: str) -> None:
        """
        Inserts the text before the character at offset pos in the existing text
        """
        if not text:
            return

        self_text = self.get_text()

        if pos < 0 or pos > len(self_text):
            raise EditTextRangeError("pos is out of range", pos, pos)

        if pos == 0:
            self.set_text(text + self_text)
        else:
            self.set_text(self_text[:pos] + text + self_text[pos:])
        self.dirty = True
