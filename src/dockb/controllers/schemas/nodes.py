"""ProseMirror node types for the wire format.

Chapter, Paragraph, and Sentence are transmitted as ProseMirror JSON trees.
Individual GET requests return the full tree from the requested node downward.
Tokens are server-only and never appear on the wire.

All attrs models use ``extra='allow'`` so that future fields (e.g. formatting
attributes on text nodes) can be added without breaking existing consumers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dockb.titles import validate_segment

# ---------------------------------------------------------------------------
# Attrs models (forward-extensible)
# ---------------------------------------------------------------------------


class SentenceAttrs(BaseModel):
    """Attributes carried on a sentence node."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None


class ParagraphAttrs(BaseModel):
    """Attributes carried on a paragraph node."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None


class ChapterAttrs(BaseModel):
    """Attributes carried on a chapter node."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str = Field(min_length=1)
    act: str = ""
    category: Literal["Chapter", "Character"] = "Chapter"

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        """Reject a title that is blank or could escape the chapter directory."""
        if not value.strip():
            raise ValueError("title must not be blank")
        validate_segment(value)
        return value

    @field_validator("act")
    @classmethod
    def act_is_a_safe_segment(cls, value: str) -> str:
        """Reject an act that could escape the chapter directory.

        An empty act is legitimate — it maps to the reserved ``Act None``
        directory — so only the path-safety rule applies, not the blank rule
        that titles carry. The store likewise validates the act directory it
        derives rather than the raw act, so both sides see the same value.
        """
        if value:
            validate_segment(value)
        return value


class ChapterSummary(BaseModel):
    """Lightweight chapter reference used in document summaries (attrs only)."""

    id: str
    title: str
    act: str = ""
    category: Literal["Chapter", "Character"] = "Chapter"


# ---------------------------------------------------------------------------
# ProseMirror node types
# ---------------------------------------------------------------------------


class TextNode(BaseModel):
    """Inline text node.  ``type`` is always ``"text"``."""

    type: Literal["text"] = "text"
    text: str
    # attrs will be added in future per the spec


class SentenceNode(BaseModel):
    """ProseMirror sentence node containing inline text."""

    type: Literal["sentence"] = "sentence"
    attrs: SentenceAttrs
    content: list[TextNode]


class ParagraphNode(BaseModel):
    """ProseMirror paragraph node containing sentences."""

    type: Literal["paragraph"] = "paragraph"
    attrs: ParagraphAttrs
    content: list[SentenceNode]


class ChapterNode(BaseModel):
    """ProseMirror chapter node containing paragraphs."""

    type: Literal["chapter"] = "chapter"
    attrs: ChapterAttrs
    content: list[ParagraphNode]
