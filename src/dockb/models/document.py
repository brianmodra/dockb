from __future__ import annotations
from pydantic import Field
from .base import DockbModel
from dockb.models.chapter import Chapter


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

    chapters: list[Chapter] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        self.text = text
