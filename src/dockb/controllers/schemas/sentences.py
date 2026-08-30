"""Sentence request / response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from dockb.controllers.schemas.nodes import SentenceAttrs, TextNode


class SentenceRelations(BaseModel):
    """Relations block accepted by POST /api/sentences."""

    paragraph_id: str
    after_sentence_id: str | None = None


class UpdateSentenceRelations(BaseModel):
    """Optional relations block accepted by PUT /api/sentences/{id}.

    When omitted the sentence stays in its current paragraph and position.
    """

    paragraph_id: str | None = None
    after_sentence_id: str | None = None


class CreateSentenceRequest(BaseModel):
    """POST /api/sentences request body."""

    attrs: SentenceAttrs
    content: list[TextNode] = Field(min_length=0)
    relations: SentenceRelations


class UpdateSentenceRequest(BaseModel):
    """PUT /api/sentences/{id} request body."""

    attrs: SentenceAttrs | None = None
    content: list[TextNode] = Field(min_length=0)
    relations: UpdateSentenceRelations | None = None
