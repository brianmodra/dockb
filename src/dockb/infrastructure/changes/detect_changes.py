"""Detect paragraph-level changes between a hydrated chapter and a markdown file."""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from dockb.infrastructure.markdown import front_matter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph

_SPAN_RE = re.compile(r"<span\b([^>]*)>(.*?)</span>", re.DOTALL)


@dataclass
class ChangedParagraph:
    """A paragraph present on both sides whose text differs."""

    par_id: str
    text: str


@dataclass
class NewParagraph:
    """A paragraph present only in the new markdown (no id, or id unknown to the DB)."""

    text: str
    after_id: str | None = None
    at_start: bool = False


@dataclass
class ChapterDiff:
    """The result of diffing a chapter: what to rehydrate, add, and delete.

    ``chapter_id`` is the resolved chapter identity — the front-matter id of the
    diffed file when present, otherwise the id assigned by ``create_chapter``.
    ``title`` is the front-matter title, else ``title_fallback``. ``front_id`` is
    the file's front-matter id, if any; ``created`` is True when ``create_chapter``
    supplied the old side.
    """

    changed: list[ChangedParagraph] = field(default_factory=list)
    new: list[NewParagraph] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    chapter_id: str = ""
    title: str = ""
    front_id: str | None = None
    created: bool = False

    def __bool__(self) -> bool:
        return bool(self.changed or self.new or self.deleted)


def detect_changes(
    new_markdown: str,
    get_chapter: Callable[[str], Chapter | None],
    create_chapter: Callable[[str | None, str], Chapter],
    title_fallback: str = "",
) -> ChapterDiff:
    """Classify paragraph changes between a chapter and a new markdown file.

    Only the *new* markdown is parsed. The old side is a hydrated chapter
    resolved through ``get_chapter`` (its paragraphs' ``get_text``) and never
    re-parsed. A file with no YAML front matter (or with an id no
    chapter answers for) has no old side: ``create_chapter`` supplies the empty
    skeleton and receives the resolved chapter title now. The resolved title is
    the front-matter ``title`` when present, else ``title_fallback``; it is also
    carried back on ``ChapterDiff.title``.
    """
    front_id, front_title, body = _extract_front_matter(new_markdown)
    title = front_title or title_fallback

    old_chapter = get_chapter(front_id) if front_id is not None else None
    created = False
    if old_chapter is None:
        old_chapter = create_chapter(front_id, title)
        created = True

    old_texts = {paragraph.id: _old_texts(paragraph) for paragraph in old_chapter.paragraphs}
    changed, new, seen_ids = _classify_blocks(body, old_texts, bool(old_chapter.paragraphs))

    return ChapterDiff(
        changed=changed,
        new=new,
        deleted=[paragraph.id for paragraph in old_chapter.paragraphs if paragraph.id not in seen_ids],
        chapter_id=old_chapter.id,
        title=title,
        front_id=front_id,
        created=created,
    )


def _classify_blocks(
    body: str,
    old_texts: dict[str, str],
    chapter_has_paragraphs: bool,
) -> tuple[list[ChangedParagraph], list[NewParagraph], set[str]]:
    """Classify every block in *body*, returning ``(changed, new, seen_ids)``.

    *anchor* is the nearest preceding block that survives (an unchanged or
    changed paragraph); consecutive new blocks all carry the same anchor, and a
    leading-new block is flagged ``at_start`` only when the old chapter already
    has paragraphs (so placement at the start matters).
    """
    changed: list[ChangedParagraph] = []
    new: list[NewParagraph] = []
    seen_ids: set[str] = set()
    anchor: str | None = None
    for block in (part.strip() for part in body.split("\n\n")):
        if not block:
            continue
        par_id, text = _parse_block(block)
        if not text.strip():
            if par_id is not None:
                seen_ids.add(par_id)
            continue
        if par_id is None or par_id not in old_texts:
            new.append(
                NewParagraph(
                    text,
                    after_id=anchor,
                    at_start=anchor is None and chapter_has_paragraphs,
                )
            )
        else:
            if text != old_texts[par_id]:
                changed.append(ChangedParagraph(par_id, text))
            anchor = par_id
        if par_id is not None:
            seen_ids.add(par_id)

    return changed, new, seen_ids


def _old_texts(paragraph: Paragraph) -> str:
    """Paragraph text for one hydrated paragraph (its ``get_text``)."""
    return paragraph.get_text()


def _parse_block(block: str) -> tuple[str | None, str]:
    """Parse one paragraph block into ``(par_id, text)``.

    One identity span usually wraps the whole paragraph; its inner text minus the
    structural newlines after the open tag and before the close tag is the
    paragraph text. Loose text before, between, and after spans is kept at its
    position, so hand-typed content appended after the closing span still belongs
    to the same paragraph.
    """
    matches = list(_SPAN_RE.finditer(block))
    if not matches:
        return None, block
    if len(matches) == 1 and not _span_attr(matches[0].group(1), "data-par-id"):
        return None, block

    parts: list[str] = []
    par_id: str | None = None
    position = 0
    for match in matches:
        parts.append(block[position : match.start()])
        tag = match.group(1)
        span_par_id = _span_attr(tag, "data-par-id")
        if par_id is None and span_par_id:
            par_id = span_par_id
        parts.append(html.unescape(match.group(2)).strip("\n"))
        position = match.end()
    parts.append(block[position:])

    if par_id is None:
        return None, "".join(parts)
    return par_id, "".join(parts)


def _span_attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    if not match:
        return None
    return html.unescape(match.group(1))


def _extract_front_matter(content: str) -> tuple[str | None, str | None, str]:
    """Read an optional YAML front matter block; return its ``id``, ``title``, and the body.

    Front matter is optional: a file without it is a new chapter (no ``id``).
    A file that opens with ``---`` but is missing the closing ``---`` is malformed.
    """
    attrs, body = front_matter.parse(content)
    front_id = attrs.get("id")
    front_title = attrs.get("title")
    return (
        str(front_id) if front_id is not None else None,
        str(front_title) if front_title is not None else None,
        body,
    )
