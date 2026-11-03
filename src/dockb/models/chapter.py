"""Chapter model for document hierarchy."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dockb.models.paragraph import Paragraph
from dockb.models.utils.dockb_collection import DockbCollection, DockbModelBase, InsertionMode

from .base import DockbModel


class Chapter(DockbModel):
    """A chapter containing a list of paragraphs.

    ``category`` is ``Chapter`` (the manuscript, the default) or ``Character``
    (supporting material). A ``Character`` chapter is never published.
    """

    title: str = ""
    act: str = ""
    category: Literal["Chapter", "Character"] = "Chapter"
    # Character-chapter properties (hand-maintained in the file's front matter,
    # meaningful only for category "Character"): who this character is, for POV
    # matching. Empty/None on manuscript chapters.
    first_name: str = ""
    surname: str = ""
    middle_names: list[str] = Field(default_factory=list)
    nicknames: list[str] = Field(default_factory=list)
    age: int | None = None
    location: str = ""
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
