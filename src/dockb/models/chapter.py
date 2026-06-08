"""Chapter model for document hierarchy."""

from __future__ import annotations

from pydantic import Field

from dockb.models.paragraph import Paragraph
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Chapter(DockbModel):
    """A chapter containing a list of paragraphs."""

    paragraphs: DockbCollection[Paragraph] = Field(default_factory=DockbCollection)

    def get_text(self) -> str:
        if self.dirty:
            return self.text
        if not self.paragraphs:
            return self.text
        return "".join(paragraph.get_text() for paragraph in self.paragraphs)

    def clear_semantics(self) -> None:
        for paragraph in self.paragraphs:
            paragraph.clear_semantics()
        self.paragraphs.clear()

    def delete_child(self, child_id: str) -> bool:
        if self.paragraphs.delete(child_id):
            return True
        for paragraph in self.paragraphs:
            if paragraph.delete_child(child_id):
                return True
        return False

    def insert_child(self, child: DockbModelBase, insertion_mode: InsertionMode, after: str | None = None) -> None:
        if not isinstance(child, Paragraph):
            raise TypeError(f"Expected Paragraph, got {type(child).__name__}")
        self.paragraphs.insert(child, insertion_mode, after)
