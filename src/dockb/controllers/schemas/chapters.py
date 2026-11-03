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
    warnings: list[str] = Field(default_factory=list)


class ChapterDocumentRequest(BaseModel):
    """PUT /api/chapters/{id}/document request body — the editor's loose text."""

    content: str


class ChapterDocumentResponse(BaseModel):
    """GET/PUT /api/chapters/{id}/document response — canonical text plus change summary."""

    content: str
    summary: ChapterImportSummaryWire | None = None
    warnings: list[str] = Field(default_factory=list)


class PovRequest(BaseModel):
    """POST /api/chapters/{id}/pov request body — the typed character name."""

    name: str = ""


class PovCharacterWire(BaseModel):
    """The POV character the chapter is written from."""

    id: str
    title: str


class PovResponse(BaseModel):
    """POST /api/chapters/{id}/pov response.

    ``applied`` is True when the pov was set (``pov`` names the character) or
    cleared (``pov`` null). False means nothing was applied: ``warning`` says
    why, and ``pov`` carries the suggested character when there is one.
    """

    applied: bool
    pov: PovCharacterWire | None = None
    warning: str | None = None
