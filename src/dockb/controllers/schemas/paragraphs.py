"""Paragraph request / response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from dockb.controllers.schemas.nodes import ParagraphAttrs, SentenceNode


class ParagraphRelations(BaseModel):
    """Relations block accepted by POST /api/paragraphs."""

    chapter_id: str
    after_paragraph_id: str | None = None


class UpdateParagraphRelations(BaseModel):
    """Optional relations block accepted by PUT /api/paragraphs/{id}.

    When omitted the paragraph stays in its current chapter and position.
    """

    chapter_id: str | None = None
    after_paragraph_id: str | None = None


class CreateParagraphRequest(BaseModel):
    """POST /api/paragraphs request body."""

    attrs: ParagraphAttrs
    content: list[SentenceNode] = Field(min_length=1)
    relations: ParagraphRelations


class UpdateParagraphRequest(BaseModel):
    """PUT /api/paragraphs/{id} request body."""

    attrs: ParagraphAttrs
    content: list[SentenceNode] = Field(min_length=1)
    relations: UpdateParagraphRelations | None = None
