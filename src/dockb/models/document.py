from __future__ import annotations

from pydantic import Field

from dockb.models.chapter import Chapter

from .base import DockbModel


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
        if self.dirty:
            return self.text
        if not self.chapters:
            return self.text
        return "".join(chapter.getText() for chapter in self.chapters)

    def set_text(self, text: str, delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text
        if delay_semantics:
            return

