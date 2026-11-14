"""ProseMirror node types for the wire format.

Chapter, Paragraph, and Sentence are transmitted as ProseMirror JSON trees.
Individual GET requests return the full tree from the requested node downward.
Tokens are server-only and never appear on the wire.

All attrs models use ``extra='allow'`` so that future fields can be added
without breaking existing consumers. Text nodes carry at most one ``format``
mark, and paragraphs carry their structured ``layout`` in attrs.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from dockb.models.formatting import (
    Family,
    FormatRun,
    LayoutKind,
    LayoutVariant,
    Style,
    Weight,
    validate_layout,
    validate_size,
)
from dockb.titles import validate_segment

# ---------------------------------------------------------------------------
# Attrs models (forward-extensible)
# ---------------------------------------------------------------------------


class SentenceAttrs(BaseModel):
    """Attributes carried on a sentence node."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None


class ParagraphLayout(BaseModel):
    """Structured paragraph layout carried on the wire."""

    model_config = ConfigDict(extra="forbid")

    kind: LayoutKind = "normal"
    variant: LayoutVariant = ""

    @model_validator(mode="after")
    def layout_is_consistent(self) -> ParagraphLayout:
        """Require a variant exactly when the paragraph is quoted."""
        validate_layout(self.kind, self.variant)
        return self


class ParagraphAttrs(BaseModel):
    """Attributes carried on a paragraph node."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    layout: ParagraphLayout = Field(default_factory=ParagraphLayout)


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


class FormatMarkAttrs(BaseModel):
    """The inline formatting attributes on a ``format`` mark."""

    model_config = ConfigDict(extra="forbid")

    style: Style = Style._
    weight: Weight = Weight._
    family: Family = Family._
    size: str = ""

    @field_validator("size")
    @classmethod
    def size_is_valid(cls, value: str) -> str:
        """Reject a size that is not a positive ``em`` length."""
        return validate_size(value)

    def is_unset(self) -> bool:
        """Return True when the mark carries no formatting."""
        return self.style is Style._ and self.weight is Weight._ and self.family is Family._ and not self.size

    def to_run(self, start: int, end: int) -> FormatRun:
        """Build a character-range run with these attributes."""
        return FormatRun(start, end, style=self.style, weight=self.weight, family=self.family, size=self.size)


class FormatMark(BaseModel):
    """The single inline formatting mark type carried by a text node."""

    type: Literal["format"] = "format"
    attrs: FormatMarkAttrs


class TextNode(BaseModel):
    """Inline text node.  ``type`` is always ``"text"``."""

    type: Literal["text"] = "text"
    text: str
    marks: list[FormatMark] = Field(default_factory=list)

    @model_validator(mode="after")
    def at_most_one_format_mark(self) -> TextNode:
        """Reject more than one format mark on one text node."""
        if len(self.marks) > 1:
            raise ValueError("a text node carries at most one format mark")
        return self

    @model_serializer(mode="wrap")
    def omit_empty_marks(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Keep unformatted text nodes byte-identical to the old wire shape."""
        data: dict[str, Any] = handler(self)
        if not self.marks:
            data.pop("marks", None)
        return data


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
