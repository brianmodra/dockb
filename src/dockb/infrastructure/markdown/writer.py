"""Serialize a Chapter into the canonical span-form markdown."""

from __future__ import annotations

import html
from pathlib import Path

from spacy.language import Language

from dockb.infrastructure.markdown import front_matter, layout
from dockb.models.chapter import Chapter
from dockb.models.formatting import LayoutKind, LayoutVariant
from dockb.models.paragraph import Paragraph


def serialize_body(chapter: Chapter, _nlp: Language | None) -> str:
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
    nlp: Language | None,
    attrs: dict[str, object] | None = None,
) -> str:
    """Render *chapter* as a complete markdown file: front matter block plus body.

    *attrs* becomes the front matter; it defaults to the chapter's own ``id``
    and ``title`` (plus ``act`` when set and ``category`` always), joined by the
    chapter's character properties when it has any. The body is
    appended after a blank
    line (or omitted entirely when the chapter has no text), mirroring the
    history snapshot format.
    """
    if attrs is not None:
        front_attrs = dict(attrs)
        front_attrs.update(character_front_matter(chapter))
    else:
        front_attrs = {"id": chapter.id, "title": chapter.title}
        if chapter.act:
            front_attrs["act"] = chapter.act
        front_attrs["category"] = chapter.category
        front_attrs.update(character_front_matter(chapter))
    body = serialize_body(chapter, nlp)
    parts = [front_matter.render(front_attrs)]
    if body:
        parts.append("\n")
        parts.append(body)
        parts.append("\n")
    return "".join(parts)


def character_front_matter(chapter: Chapter) -> dict[str, object]:
    """The chapter's character properties as front matter, only those that are set.

    A manuscript chapter has none of them set, so its front matter stays
    byte-for-byte what it always was.
    """
    props: dict[str, object] = {}
    if chapter.first_name:
        props["first_name"] = chapter.first_name
    if chapter.surname:
        props["surname"] = chapter.surname
    if chapter.middle_names:
        props["middle_names"] = list(chapter.middle_names)
    if chapter.nicknames:
        props["nicknames"] = list(chapter.nicknames)
    if chapter.age is not None:
        props["age"] = chapter.age
    if chapter.location:
        props["location"] = chapter.location
    return props


def write_chapter_markdown(
    chapter: Chapter,
    path: str | Path,
    nlp: Language | None,
    attrs: dict[str, object] | None = None,
) -> None:
    """Write *chapter*'s rendered markdown to *path*, overwriting it."""
    Path(path).write_text(render_chapter_markdown(chapter, nlp, attrs=attrs), encoding="utf-8")


def _serialize_paragraph(paragraph: Paragraph) -> str:
    """Serialize one paragraph as a single identity span around its sentence lines."""
    if not paragraph.sentences:
        return _serialize_plain_text(
            paragraph.get_text(),
            layout_kind=paragraph.layout_kind,
            layout_variant=paragraph.layout_variant,
        )
    lines = [sentence.get_text().rstrip() for sentence in paragraph.sentences if sentence.get_text().strip()]
    if not lines:
        return ""
    return _paragraph_span(
        paragraph.id,
        "\n".join(lines),
        layout_kind=paragraph.layout_kind,
        layout_variant=paragraph.layout_variant,
    )


def _serialize_plain_text(text: str, layout_kind: LayoutKind = "normal", layout_variant: LayoutVariant = "") -> str:
    """Wrap span-free text in a fresh-id paragraph identity span."""
    if not text.strip():
        return ""
    return _paragraph_span(str(Paragraph().id), text, layout_kind=layout_kind, layout_variant=layout_variant)


def _paragraph_span(paragraph_id: str, text: str, layout_kind: LayoutKind = "normal", layout_variant: LayoutVariant = "") -> str:
    par_id = html.escape(paragraph_id, quote=True)
    escaped = html.escape(text, quote=True)
    layout_attrs = layout.render_layout_attributes(layout_kind, layout_variant)
    return f'<span data-par-id="{par_id}"{layout_attrs}>\n{escaped}\n</span>'
