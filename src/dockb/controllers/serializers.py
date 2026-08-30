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
    ParagraphAttrs,
    ParagraphNode,
    SentenceAttrs,
    SentenceNode,
    TextNode,
)

if TYPE_CHECKING:
    from dockb.models.chapter import Chapter
    from dockb.models.document import Document
    from dockb.models.paragraph import Paragraph
    from dockb.models.sentence import Sentence


def serialize_sentence(sentence: Sentence) -> SentenceNode:
    """Convert a Sentence model into a ProseMirror SentenceNode."""
    text = sentence.get_text()
    content = [TextNode(text=text)] if text else []
    return SentenceNode(
        attrs=SentenceAttrs(id=sentence.id),
        content=content,
    )


def serialize_paragraph(paragraph: Paragraph) -> ParagraphNode:
    """Convert a Paragraph model into a ProseMirror ParagraphNode."""
    return ParagraphNode(
        attrs=ParagraphAttrs(id=paragraph.id),
        content=[serialize_sentence(s) for s in paragraph.sentences],
    )


def serialize_chapter(chapter: Chapter) -> ChapterNode:
    """Convert a Chapter model into a ProseMirror ChapterNode."""
    return ChapterNode(
        attrs=ChapterAttrs(id=chapter.id, title=chapter.title),
        content=[serialize_paragraph(p) for p in chapter.paragraphs],
    )


def serialize_chapter_summary(chapter: Chapter) -> ChapterSummary:
    """Extract a lightweight ChapterSummary (attrs only) from a Chapter model."""
    return ChapterSummary(id=chapter.id, title=chapter.title)


def serialize_document(document: Document) -> dict[str, Any]:
    """Convert a Document model into the plain-JSON response format.

    Returns a dict matching ``DocumentResponse`` (attrs + chapter_summaries,
    no child content).
    """
    return DocumentResponse(
        attrs=DocumentAttrs(id=document.id, title=document.title, author=document.author),
        chapter_summaries=[serialize_chapter_summary(ch) for ch in document.chapters],
    ).model_dump()
