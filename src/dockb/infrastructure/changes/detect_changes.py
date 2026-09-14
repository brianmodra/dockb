"""Detect paragraph-level changes between a hydrated chapter and a markdown file."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import yaml
from spacy.language import Language

from dockb.exceptions import ChapterMismatchError
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph

_SPAN_RE = re.compile(r"<span\b([^>]*)>(.*?)</span>", re.DOTALL)


@dataclass
class ChangedParagraph:
    """A paragraph present on both sides whose sentence texts differ."""

    par_id: str
    sentence_texts: list[str]


@dataclass
class NewParagraph:
    """A paragraph present only in the new markdown (no id, or id unknown to the DB)."""

    sentence_texts: list[str]


@dataclass
class ChapterDiff:
    """The result of diffing a chapter: what to rehydrate, add, and delete."""

    changed: list[ChangedParagraph] = field(default_factory=list)
    new: list[NewParagraph] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.changed or self.new or self.deleted)


def detect_changes(old_chapter: Chapter, new_markdown: str, nlp: Language) -> ChapterDiff:
    """Classify paragraph changes between a hydrated chapter and a new markdown file.

    Only the *new* markdown is parsed. The old side is read from the hydrated
    ``old_chapter`` (its paragraphs' ``get_text``-ed sentences) and never re-parsed.
    The file's YAML front matter must identify the chapter being diffed.
    """
    body = _strip_front_matter(new_markdown, old_chapter.id)
    old_texts = {paragraph.id: _old_texts(paragraph) for paragraph in old_chapter.paragraphs}

    diff = ChapterDiff()
    seen_ids: set[str] = set()
    for block in (part.strip() for part in body.split("\n\n")):
        if not block:
            continue
        par_id, sentence_texts = _parse_block(block, nlp)
        if par_id is None or par_id not in old_texts:
            diff.new.append(NewParagraph(sentence_texts))
        elif sentence_texts != old_texts[par_id]:
            diff.changed.append(ChangedParagraph(par_id, sentence_texts))
        if par_id is not None:
            seen_ids.add(par_id)

    diff.deleted = [paragraph.id for paragraph in old_chapter.paragraphs if paragraph.id not in seen_ids]
    return diff


def _old_texts(paragraph: Paragraph) -> list[str]:
    """Sentence texts for one hydrated paragraph, opaque string if it holds no sentences."""
    if not paragraph.sentences:
        return [paragraph.get_text()]
    return [sentence.get_text() for sentence in paragraph.sentences]


def _parse_block(block: str, nlp: Language) -> tuple[str | None, list[str]]:
    """Parse one paragraph block into ``(par_id, sentence_texts)``.

    Span inner content is the sentence text; ``data-par-id`` is identity only.
    Loose text around spans is NLP-split in place (mirroring ``SnapshotReader``).
    """
    matches = list(_SPAN_RE.finditer(block))
    if not matches:
        return None, _split_sentences(block, nlp)

    sentence_texts: list[str] = []
    par_id: str | None = None
    position = 0
    for match in matches:
        gap = block[position : match.start()]
        if gap.strip():
            sentence_texts.extend(_split_sentences(gap, nlp))

        tag = match.group(1)
        inner = html.unescape(match.group(2))
        span_par_id = _span_attr(tag, "data-par-id")
        if par_id is None and span_par_id:
            par_id = span_par_id
        if inner.strip():
            sentence_texts.append(inner)
        position = match.end()

    tail = block[position:]
    if tail.strip():
        sentence_texts.extend(_split_sentences(tail, nlp))

    return par_id, sentence_texts


def _split_sentences(text: str, nlp: Language) -> list[str]:
    """Split *text* on spaCy sentence boundaries, keeping whitespace up to the next sentence."""
    spans = list(nlp(text).sents)
    sentences = []
    for idx, span in enumerate(spans):
        end = spans[idx + 1].start_char if idx + 1 < len(spans) else len(text)
        sentence_text = text[span.start_char : end]
        if sentence_text.strip():
            sentences.append(sentence_text)
    return sentences


def _span_attr(tag: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    if not match:
        return None
    return html.unescape(match.group(1))


def _strip_front_matter(content: str, chapter_id: str) -> str:
    """Read the YAML front matter, verify it identifies *chapter_id*, and return the body."""
    stripped = content.strip()
    if not stripped.startswith("---"):
        raise ChapterMismatchError("Snapshot file does not start with YAML front matter")

    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise ChapterMismatchError("Snapshot file is missing closing '---' for front matter")

    attrs = yaml.safe_load(parts[1]) or {}
    file_id = attrs.get("id")
    if file_id != chapter_id:
        raise ChapterMismatchError(f"Chapter id mismatch: file identifies '{file_id}', expected '{chapter_id}'")
    return parts[2]
