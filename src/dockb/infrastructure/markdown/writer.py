"""Serialize a Chapter into the canonical span-form markdown."""

from __future__ import annotations

import html
from pathlib import Path

from spacy.language import Language

from dockb.infrastructure.markdown import front_matter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph


def serialize_body(chapter: Chapter, _nlp: Language) -> str:
    """Serialize *chapter*'s text as one id-span per paragraph, blank-line separated.

    A ``dirty`` chapter keeps its raw text: each blank-line block becomes a fresh
    id-span paragraph. Otherwise every paragraph is a single ``data-par-id`` span
    holding its sentences, one per line.
    """
    if chapter.dirty:
        blocks = [_serialize_plain_text(block) for block in chapter.text.split("\n\n")]
    elif chapter.paragraphs:
        blocks = [_serialize_paragraph(paragraph) for paragraph in chapter.paragraphs]
    else:
        blocks = []
    return "\n\n".join(block for block in blocks if block)


def render_chapter_markdown(
    chapter: Chapter,
    nlp: Language,
    attrs: dict[str, object] | None = None,
) -> str:
    """Render *chapter* as a complete markdown file: front matter block plus body.

    *attrs* becomes the front matter; it defaults to the chapter's own ``id`` and
    ``title``. The body is appended after a blank line (or omitted entirely when
    the chapter has no text), mirroring the history snapshot format.
    """
    front_attrs = dict(attrs) if attrs is not None else {"id": chapter.id, "title": chapter.title}
    body = serialize_body(chapter, nlp)
    parts = [front_matter.render(front_attrs)]
    if body:
        parts.append("\n")
        parts.append(body)
        parts.append("\n")
    return "".join(parts)


def write_chapter_markdown(
    chapter: Chapter,
    path: str | Path,
    nlp: Language,
    attrs: dict[str, object] | None = None,
) -> None:
    """Write *chapter*'s rendered markdown to *path*, overwriting it."""
    Path(path).write_text(render_chapter_markdown(chapter, nlp, attrs=attrs), encoding="utf-8")


def _serialize_paragraph(paragraph: Paragraph) -> str:
    """Serialize one paragraph as a single identity span around its sentence lines."""
    if not paragraph.sentences:
        return _serialize_plain_text(paragraph.get_text())
    lines = [sentence.get_text().rstrip() for sentence in paragraph.sentences if sentence.get_text().strip()]
    if not lines:
        return ""
    return _paragraph_span(paragraph.id, "\n".join(lines))


def _serialize_plain_text(text: str) -> str:
    """Wrap span-free text in a fresh-id paragraph identity span."""
    if not text.strip():
        return ""
    return _paragraph_span(str(Paragraph().id), text)


def _paragraph_span(paragraph_id: str, text: str) -> str:
    par_id = html.escape(paragraph_id, quote=True)
    escaped = html.escape(text, quote=True)
    return f'<span data-par-id="{par_id}">\n{escaped}\n</span>'
