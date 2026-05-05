from __future__ import annotations
from .base import DockbModel
import uuid
from pydantic import Field, PositiveInt
from dockb.models.paragraph import Paragraph

class Chapter(DockbModel):
    id: str = uuid.uuid4()
    paragraphs: list[Paragraph] = Field(default_factory=list)
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
        return

    def apply_append_text(self, text: str) -> None:
        """
        Appends the text after the end of the existing text
        """
        return

    def apply_insert_text(self, pos: int, text: str) -> None:
        """
        Inserts the text before the character at offset pos in the existing text
        """
        return