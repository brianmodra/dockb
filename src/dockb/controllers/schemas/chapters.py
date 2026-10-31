"""Chapter request / response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from dockb.controllers.schemas.nodes import ChapterAttrs


class ChapterRelations(BaseModel):
    """Relations block accepted by POST /api/chapters."""

    document_id: str
    after_chapter_id: str | None = None


class CreateChapterRequest(BaseModel):
    """POST /api/chapters request body."""

    attrs: ChapterAttrs
    relations: ChapterRelations


class UpdateChapterRequest(BaseModel):
    """PUT /api/chapters/{id} request body."""

    attrs: ChapterAttrs


class ReorderChapterRequest(BaseModel):
    """POST /api/chapters/{id}/reorder request body."""

    after_chapter_id: str | None = None


class RenumberChaptersRequest(BaseModel):
    """POST /api/chapters/renumber request body.

    ``start`` is the number the first chapter takes: 1 by default, 0 when the
    writer counts from zero.
    """

    document_id: str
    start: int = Field(default=1, ge=0)


class ChapterImportSummaryWire(BaseModel):
    """What a save imported into the graph (omitted on read-only GETs)."""

    created: bool
    changed: int
    added: int
    deleted: int


class ChapterDocumentRequest(BaseModel):
    """PUT /api/chapters/{id}/document request body — the editor's loose text."""

    content: str


class ChapterDocumentResponse(BaseModel):
    """GET/PUT /api/chapters/{id}/document response — canonical text plus change summary."""

    content: str
    summary: ChapterImportSummaryWire | None = None
