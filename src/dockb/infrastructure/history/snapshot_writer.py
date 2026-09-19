"""Serialize a Chapter to markdown and persist via git."""

from __future__ import annotations

import subprocess
from pathlib import Path

from spacy.language import Language

from dockb.exceptions import SnapshotError
from dockb.infrastructure.markdown import writer as markdown_writer
from dockb.models.chapter import Chapter


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
        return markdown_writer.render_chapter_markdown(chapter, self._nlp, attrs=self._front_matter_attrs(chapter))

    def _front_matter_attrs(self, chapter: Chapter) -> dict[str, object]:
        attrs: dict[str, object] = {"id": chapter.id, "title": chapter.title}
        extras = getattr(chapter, "model_extra", None) or {}
        for key, value in extras.items():
            attrs[key] = value
        return attrs

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
