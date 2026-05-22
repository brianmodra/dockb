"""Document model representing the top-level document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.chapter import Chapter

from .base import DockbModel


class Document(DockbModel):
    """
    This class holds the data for a document.
    The entire document is stored in the text parameter.
    Chapter extraction and Chapter object creation is handled externally.
    Semantic processing only starts when triggered and when dirty is True.

    This class will not modify the Chapters list, but after an apply_...
    function is called, it will set dirty=True.
    """

    chapters: list[Chapter] = Field(default_factory=list)
    text: str = ""

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.chapters:
            return self.text
        return "".join(chapter.get_text() for chapter in self.chapters)

    def set_text(self, text: str, _delay_semantics: bool = False) -> None:
        self.dirty = True
        self.text = text

    def clear_semantics(self) -> None:
        for chapter in self.chapters:
            chapter.clear_semantics()
        self.chapters.clear()
