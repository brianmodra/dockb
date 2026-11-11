"""Schemas for a document's proofreading glossary."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GlossaryRequest(BaseModel):
    """The words to store as accepted for the document."""

    words: list[str] = Field(default_factory=list)


class GlossaryWordRequest(BaseModel):
    """One word to add to the document's accepted words."""

    word: str


class GlossaryResponse(BaseModel):
    """The document's stored accepted words."""

    words: list[str] = Field(default_factory=list)
