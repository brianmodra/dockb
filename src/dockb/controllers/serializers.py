"""Convert in-memory model objects to ProseMirror JSON wire format.

Tokens are server-only and never appear on the wire.  Sentence text is
reconstructed from tokens via ``Sentence.get_text()`` and emitted as a
single ``TextNode``.  If the sentence is dirty (unsaved edit) the raw
``text`` field is used instead.

Document is **not** a ProseMirror node — it serialises to plain JSON with
``attrs`` and a flat list of ``ChapterSummary`` objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dockb.controllers.schemas.documents import DocumentAttrs, DocumentResponse
from dockb.controllers.schemas.nodes import (
    ChapterAttrs,
    ChapterNode,
    ChapterSummary,
    FormatMark,
    FormatMarkAttrs,
    ParagraphAttrs,
    ParagraphLayout,
    ParagraphNode,
    SentenceAttrs,
    SentenceNode,
    TextNode,
)
from dockb.models.formatting import Family, Style, Weight

if TYPE_CHECKING:
    from dockb.models.chapter import Chapter
    from dockb.models.document import Document
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence
    from dockb.models.token import Token

FormatKey = tuple[Style, Weight, Family, str]


def _marks_for(key: FormatKey) -> list[FormatMark]:
    """Build the wire mark for one formatting key, or no marks when unset."""
    attrs = FormatMarkAttrs(style=key[0], weight=key[1], family=key[2], size=key[3])
    return [] if attrs.is_unset() else [FormatMark(attrs=attrs)]


def _serialize_tokens(tokens: list[Token]) -> list[TextNode]:
    """Group consecutive tokens with equal formatting into text nodes."""
    grouped: list[tuple[FormatKey, str]] = []
    for token in tokens:
        text = token.text + token.trailing_ws
        if not text:
            continue
        key = token.format_key()
        if grouped and grouped[-1][0] == key:
            grouped[-1] = (key, grouped[-1][1] + text)
        else:
            grouped.append((key, text))
    return [TextNode(text=text, marks=_marks_for(key)) for key, text in grouped]


def serialize_sentence(sentence: Sentence) -> SentenceNode:
    """Convert a Sentence model into a ProseMirror SentenceNode."""
    if sentence.dirty or not sentence.tokens:
        text = sentence.get_text()
        content = [TextNode(text=text)] if text else []
    else:
        content = _serialize_tokens(list(sentence.tokens))
    return SentenceNode(
        attrs=SentenceAttrs(id=sentence.id),
        content=content,
    )


def serialize_paragraph(paragraph: Paragraph) -> ParagraphNode:
    """Convert a Paragraph model into a ProseMirror ParagraphNode."""
    return ParagraphNode(
        attrs=ParagraphAttrs(
            id=paragraph.id,
            layout=ParagraphLayout(kind=paragraph.layout_kind, variant=paragraph.layout_variant),
        ),
        content=[serialize_sentence(s) for s in paragraph.sentences],
    )


def serialize_chapter(chapter: Chapter) -> ChapterNode:
    """Convert a Chapter model into a ProseMirror ChapterNode."""
    return ChapterNode(
        attrs=ChapterAttrs(
            id=chapter.id,
            title=chapter.title,
            act=chapter.act,
            category=chapter.category,
        ),
        content=[serialize_paragraph(p) for p in chapter.paragraphs],
    )


def serialize_chapter_summary(chapter: Chapter) -> ChapterSummary:
    """Extract a lightweight ChapterSummary (attrs only) from a Chapter model."""
    return ChapterSummary(id=chapter.id, title=chapter.title, act=chapter.act, category=chapter.category)


def serialize_document(document: Document) -> dict[str, Any]:
    """Convert a Document model into the plain-JSON response format.

    Returns a dict matching ``DocumentResponse`` (attrs + chapter_summaries,
    no child content).
    """
    return DocumentResponse(
        attrs=DocumentAttrs(
            id=document.id,
            title=document.title,
            author=document.author,
            narrative_perspective=document.narrative_perspective,
        ),
        chapter_summaries=[serialize_chapter_summary(ch) for ch in document.chapters],
    ).model_dump()
