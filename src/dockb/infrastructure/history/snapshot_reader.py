"""Parse a markdown snapshot back into model objects."""

from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

from spacy.language import Language

from dockb.exceptions import ChapterMismatchError, SnapshotError
from dockb.infrastructure.markdown import front_matter
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence

_SPAN_RE = re.compile(r"<span\b([^>]*)>(.*?)</span>", re.DOTALL)


class SnapshotReader:
    """Read chapter snapshots from markdown files (optionally at a specific git commit)."""

    def __init__(self, base_dir: Path, nlp: Language) -> None:
        self._base_dir = base_dir
        self._nlp = nlp

    def read(self, chapter_id: str, *, commit_id: str | None = None) -> str:
        """Return raw markdown content for *chapter_id*."""
        file_path = f"chapter-{chapter_id}.md"

        if commit_id is not None:
            content = self._git_show(commit_id, file_path)
        else:
            path = self._base_dir / file_path
            if not path.exists():
                raise SnapshotError(f"Snapshot file not found: {path}")
            content = path.read_text()

        return content

    def read_chapter(self, chapter_id: str, *, commit_id: str | None = None) -> Chapter:
        """Read and parse a snapshot into a Chapter model."""
        content = self.read(chapter_id, commit_id=commit_id)
        return self._parse(content, chapter_id)

    def _parse(self, content: str, chapter_id: str) -> Chapter:
        if not content.startswith("---"):
            raise SnapshotError("Snapshot file does not start with YAML front matter")
        try:
            attrs, body = front_matter.parse(content)
        except ChapterMismatchError as exc:
            raise SnapshotError(str(exc)) from exc

        chapter_id_from_file = str(attrs.pop("id", chapter_id))
        title = str(attrs.pop("title", ""))
        extras = attrs

        chapter = Chapter(id=chapter_id_from_file, title=title)
        chapter._snapshot_extras = extras  # pylint: disable=protected-access

        paragraphs_text = body.strip().split("\n\n") if body.strip() else []
        for para_text in paragraphs_text:
            paragraph, sentences = self._parse_paragraph(para_text.strip())
            if sentences:
                paragraph.sentences[:] = sentences
            else:
                paragraph.set_text(para_text.strip())
            chapter.paragraphs.append(paragraph)

        return chapter

    def _parse_paragraph(self, text: str) -> tuple[Paragraph, list[Sentence]]:
        """Parse one paragraph block into a Paragraph and its Sentences.

        The paragraph's UUID is restored from the ``data-par-id`` span attribute.
        The spans delimit the sentences, which receive freshly generated UUIDs.
        Any text outside spans (hand-typed or legacy files) is split with spaCy
        and assigned freshly generated UUIDs.
        """
        matches = list(_SPAN_RE.finditer(text))
        if not matches:
            return Paragraph(), self._split_sentences(text)

        sentences = []
        paragraph_id: str | None = None
        position = 0
        for match in matches:
            gap = text[position : match.start()]
            if gap.strip():
                sentences.extend(self._split_sentences(gap))

            tag = match.group(1)
            inner = html.unescape(match.group(2))
            par_id = self._span_attr(tag, "data-par-id")
            if paragraph_id is None and par_id:
                paragraph_id = par_id
            if inner.strip():
                sentences.append(Sentence(text=inner))
            position = match.end()

        tail = text[position:]
        if tail.strip():
            sentences.extend(self._split_sentences(tail))

        if paragraph_id is None:
            return Paragraph(), sentences
        return Paragraph(id=paragraph_id), sentences

    @staticmethod
    def _span_attr(tag: str, name: str) -> str | None:
        match = re.search(rf'\b{name}="([^"]*)"', tag)
        if not match:
            return None
        return html.unescape(match.group(1))

    def _split_sentences(self, text: str) -> list[Sentence]:
        """Split *text* into Sentence objects using spaCy sentence boundaries.

        Newlines are never sentence delimiters: a mid-sentence newline stays inside
        the sentence's text, and a backslash-newline hard break is preserved. Each
        sentence keeps the whitespace up to the next sentence so that
        ``Chapter.get_text()`` reproduces the file byte-for-byte.
        """
        spans = list(self._nlp(text).sents)
        sentences = []
        for idx, span in enumerate(spans):
            end = spans[idx + 1].start_char if idx + 1 < len(spans) else len(text)
            sentence_text = text[span.start_char : end]
            if sentence_text.strip():
                sentences.append(Sentence(text=sentence_text))
        return sentences

    def list_commits(self, chapter_id: str, *, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
        """Return commit history for a chapter's snapshot file.

        Returns a list of ``{"commit_id": ..., "datetime": ...}`` dicts in
        reverse chronological order (most recent first).
        """
        file_path = f"chapter-{chapter_id}.md"
        try:
            result = subprocess.run(
                ["git", "log", f"--skip={offset}", f"--max-count={limit}", "--format=%H %aI", "--", file_path],
                cwd=str(self._base_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            if "does not have any commits yet" in (exc.stderr or ""):
                return []
            raise SnapshotError(f"git log failed: {exc.stderr.strip()}") from exc

        commits = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"commit_id": parts[0], "datetime": parts[1]})
        return commits

    def _git_show(self, commit_id: str, file_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "show", f"{commit_id}:{file_path}"],
                cwd=str(self._base_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            raise SnapshotError(f"git show failed: {exc.stderr.strip()}") from exc
