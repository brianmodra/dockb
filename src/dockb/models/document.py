from __future__ import annotations
import uuid
from pydantic import Field, PositiveInt
from .base import DockbModel
from dockb.models.chapter import Chapter
from dockb.exceptions import EditTextRangeError


class Document(DockbModel):
    """
    This class holds the data for a document.
    The entire document is stored in the text parameter. (This may change later.)
    This class will not handle the process of extracting chapters from the text of the document and creating
    Chapter objects in the list. That will be handled by another class. That other class will only start
    establishing the semantics when triggered and when the dirty flag is True. Once it has done its work,
    it will set it to False.

    This class (Document) will not make changes to the list of Chapters, but after an apply_... function is called,
    it will set dirty=True.
    """

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
        text  : str
                the replacement string of text

        E.g. if it starts with "Hello World!", and this function is called with start=6 and end=10, and text="Sir"
        Then the text in the document will become "Hello Sir!".

        If the existing text is empty, you can't replace it. In that case, use apply_append_text
        """
        if end < start:
            raise EditTextRangeError("end is before start", start, end)
        if not self.text:
            raise EditTextRangeError("no text to edit", start, end)
        if start >= len(self.text) or start < 0:
            raise EditTextRangeError("start is out of range", start, end)
        if end >= len(self.text) or end < 0:
            raise EditTextRangeError("end is out of range", start, end)
        self.text = self.text[:start] + text + self.text[end + 1 :]
        self.dirty = True

    def apply_append_text(self, text: str) -> None:
        """
        Appends the text after the end of the existing text
        """
        if not text:
            return
        self.text = self.text + text
        self.dirty = True

    def apply_insert_text(self, pos: int, text: str) -> None:
        """
        Inserts the text before the character at offset pos in the existing text
        """
        if not text:
            return

        if pos < 0 or pos > len(self.text):
            raise EditTextRangeError("pos is out of range", pos, pos)

        if pos == 0:
            self.text = text + self.text
        else:
            self.text = self.text[:pos] + text + self.text[pos:]
        self.dirty = True
