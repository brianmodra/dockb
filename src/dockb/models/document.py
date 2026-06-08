"""Document model representing the top-level document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.chapter import Chapter
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Document(DockbModel):
    """
    This class holds the data for a document.
    The entire document is stored in the text parameter.
    Chapter extraction and Chapter object creation is handled externally.
    Semantic processing only starts when triggered and when dirty is True.
    """

    chapters: DockbCollection[Chapter] = Field(default_factory=DockbCollection)

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.chapters:
            return self.text
        return "".join(chapter.get_text() for chapter in self.chapters)

    def clear_semantics(self) -> None:
        for chapter in self.chapters:
            chapter.clear_semantics()
        self.chapters.clear()

    def delete_child(self, child_id: str) -> bool:
        if self.chapters.delete(child_id):
            return True
        for chapter in self.chapters:
            if chapter.delete_child(child_id):
                return True
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        if not isinstance(child, Chapter):
            raise TypeError(f"Expected Chapter, got {type(child).__name__}")
        self.chapters.insert(child, insertion_mode, after)
