"""Serialize a Chapter into the canonical span-form markdown."""

from __future__ import annotations

import html
from pathlib import Path

from spacy.language import Language

from dockb.infrastructure.markdown import front_matter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


def serialize_body(chapter: Chapter, nlp: Language) -> str:
    """Serialize *chapter*'s text as id-spanned sentence lines, blank-line separated.

    A ``dirty`` chapter keeps its raw text: it is split at blank lines and each
    paragraph re-parsed with *nlp* into fresh-id spans. Otherwise paragraphs with
    sentences are emitted as one span per sentence; a sentence-less paragraph's
    text is likewise spaCy-split.
    """
    if chapter.dirty:
        blocks = [_serialize_plain_text(block, nlp) for block in chapter.text.split("\n\n")]
    elif chapter.paragraphs:
        blocks = [_serialize_paragraph(paragraph, nlp) for paragraph in chapter.paragraphs]
    else:
        blocks = []
    return "\n\n".join(blocks)


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


def _serialize_paragraph(paragraph: Paragraph, nlp: Language) -> str:
    """Serialize one paragraph as its sentences, each in an identity span on its own line."""
    if not paragraph.sentences:
        return _serialize_plain_text(paragraph.get_text(), nlp)
    lines = [_sentence_span(sentence, paragraph.id) for sentence in paragraph.sentences]
    return "\n".join(lines)


def _serialize_plain_text(text: str, nlp: Language) -> str:
    """Wrap span-free text in fresh-id sentences, splitting with spaCy."""
    if not text.strip():
        return ""
    paragraph = Paragraph()
    paragraph.sentences[:] = _split_sentences(text, nlp)
    return _serialize_paragraph(paragraph, nlp)


def _sentence_span(sentence: Sentence, paragraph_id: str) -> str:
    par_id = html.escape(paragraph_id, quote=True)
    text = html.escape(sentence.get_text(), quote=True)
    return f'<span data-par-id="{par_id}">{text}</span>'


def _split_sentences(text: str, nlp: Language) -> list[Sentence]:
    """Split *text* into Sentence objects using spaCy sentence boundaries.

    Newlines are never sentence delimiters: a mid-sentence newline stays inside
    the sentence's text, and a backslash-newline hard break is preserved. Each
    sentence keeps the whitespace up to the next sentence.
    """
    spans = list(nlp(text).sents)
    sentences = []
    for idx, span in enumerate(spans):
        end = spans[idx + 1].start_char if idx + 1 < len(spans) else len(text)
        sentence_text = text[span.start_char : end]
        if sentence_text.strip():
            sentences.append(Sentence(text=sentence_text))
    return sentences
