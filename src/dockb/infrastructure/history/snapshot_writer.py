"""Serialize a Chapter to markdown and persist via git."""

from __future__ import annotations

import html
import subprocess
from pathlib import Path

import yaml
from spacy.language import Language

from dockb.exceptions import SnapshotError
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence


class SnapshotWriter:  # pylint: disable=too-few-public-methods
    """Write chapter snapshots as markdown files committed to a local git repo."""

    def __init__(self, base_dir: Path, nlp: Language) -> None:
        self._base_dir = base_dir
        self._nlp = nlp

    def write(self, chapter: Chapter) -> str:
        """Serialize *chapter* to markdown, write to disk, git-commit, return SHA."""
        path = self._file_path(chapter.id)
        content = self._serialize(chapter)

        path.write_text(content)

        self._git("add", str(path))
        self._git("commit", "-m", f"snapshot: {chapter.id[:8]}")
        return self._git("rev-parse", "HEAD").strip()

    def _file_path(self, chapter_id: str) -> Path:
        return self._base_dir / f"chapter-{chapter_id}.md"

    def _serialize(self, chapter: Chapter) -> str:
        front_matter = self._build_front_matter(chapter)
        body = self._build_body(chapter)
        parts = ["---\n", front_matter, "---\n"]
        if body:
            parts.append("\n")
            parts.append(body)
            parts.append("\n")
        return "".join(parts)

    def _build_front_matter(self, chapter: Chapter) -> str:
        attrs: dict[str, str | int | float | bool | None] = {"id": chapter.id, "title": chapter.title}
        extras = getattr(chapter, "model_extra", None) or {}
        for key, value in extras.items():
            attrs[key] = value
        return str(yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False))

    def _build_body(self, chapter: Chapter) -> str:
        if chapter.dirty:
            blocks = [self._serialize_plain_text(block) for block in chapter.text.split("\n\n")]
        elif chapter.paragraphs:
            blocks = [self._serialize_paragraph(paragraph) for paragraph in chapter.paragraphs]
        else:
            blocks = []
        return "\n\n".join(blocks)

    def _serialize_paragraph(self, paragraph: Paragraph) -> str:
        """Serialize one paragraph as its sentences, each in an identity span on its own line."""
        if not paragraph.sentences:
            return self._serialize_plain_text(paragraph.get_text())
        lines = [self._sentence_span(sentence, paragraph.id) for sentence in paragraph.sentences]
        return "\n".join(lines)

    def _serialize_plain_text(self, text: str) -> str:
        """Wrap span-free text in fresh-id sentences, splitting with spaCy."""
        if not text.strip():
            return ""
        paragraph = Paragraph()
        paragraph.sentences[:] = self._split_sentences(text)
        return self._serialize_paragraph(paragraph)

    def _sentence_span(self, sentence: Sentence, paragraph_id: str) -> str:
        par_id = html.escape(paragraph_id, quote=True)
        text = html.escape(sentence.get_text(), quote=True)
        return f'<span data-par-id="{par_id}">{text}</span>'

    def _split_sentences(self, text: str) -> list[Sentence]:
        """Split *text* into Sentence objects using spaCy sentence boundaries.

        Newlines are never sentence delimiters: a mid-sentence newline stays inside
        the sentence's text, and a backslash-newline hard break is preserved. Each
        sentence keeps the whitespace up to the next sentence.
        """
        spans = list(self._nlp(text).sents)
        sentences = []
        for idx, span in enumerate(spans):
            end = spans[idx + 1].start_char if idx + 1 < len(spans) else len(text)
            sentence_text = text[span.start_char : end]
            if sentence_text.strip():
                sentences.append(Sentence(text=sentence_text))
        return sentences

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self._base_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            raise SnapshotError(f"git command failed: {exc.stderr.strip()}") from exc
