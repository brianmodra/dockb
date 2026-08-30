"""Chapter request / response schemas."""

from __future__ import annotations

from pydantic import BaseModel

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
