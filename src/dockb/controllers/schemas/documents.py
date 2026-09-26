"""Document request / response schemas.

A Document is **not** a ProseMirror node.  It is plain JSON with ``attrs``
and a flat list of chapter summaries (attrs only, no child content).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dockb.controllers.schemas.nodes import ChapterSummary


class DocumentAttrs(BaseModel):
    """Attributes carried on a document.

    ``id`` is optional here: POST endpoints require it, PUT endpoints treat
    it as optional (validated at the controller layer).  ``extra='allow'``
    ensures future fields (premise, elevator_pitch, …) flow through.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str = Field(min_length=1)
    author: str

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        """Reject empty and whitespace-only titles."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class DocumentResponse(BaseModel):
    """GET /api/documents/{id} response (plain JSON, not ProseMirror)."""

    attrs: DocumentAttrs
    chapter_summaries: list[ChapterSummary]


class DocumentSummary(BaseModel):
    """Summary returned by GET /api/documents (list endpoint)."""

    id: str
    title: str
    author: str


class CreateDocumentRequest(BaseModel):
    """POST /api/documents request body."""

    attrs: DocumentAttrs


class UpdateDocumentRequest(BaseModel):
    """PUT /api/documents/{id} request body."""

    attrs: DocumentAttrs
