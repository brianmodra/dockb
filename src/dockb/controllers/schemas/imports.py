"""Wire formats for the import endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dockb.services.markdown_import import ChapterImportSummary


class ImportSummaryWire(BaseModel):
    """What importing one chapter file persisted.

    Carries the chapter's identity and title, which the save response's summary
    can leave implicit because the chapter is already known there: a caller that
    uploaded a directory needs to know which chapters now exist and what they are
    called.
    """

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    title: str
    category: str
    created: bool
    changed: int
    added: int
    deleted: int

    @classmethod
    def from_summary(cls, summary: ChapterImportSummary) -> ImportSummaryWire:
        """Build the wire form of a chapter import summary."""
        return cls(
            chapter_id=summary.chapter_id,
            title=summary.title,
            category=summary.category,
            created=summary.created,
            changed=summary.changed,
            added=summary.added,
            deleted=summary.deleted,
        )


class ImportResponse(BaseModel):
    """POST /api/import response — one summary per imported chapter file."""

    model_config = ConfigDict(extra="forbid")

    imports: list[ImportSummaryWire]
