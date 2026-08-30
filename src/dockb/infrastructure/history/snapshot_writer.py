"""Serialize a Chapter to markdown and persist via git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from dockb.exceptions import SnapshotError
from dockb.models.chapter import Chapter


class SnapshotWriter:  # pylint: disable=too-few-public-methods
    """Write chapter snapshots as markdown files committed to a local git repo."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

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
            paragraphs = chapter.text.split("\n\n")
        elif chapter.paragraphs:
            paragraphs = [p.get_text() for p in chapter.paragraphs]
        else:
            paragraphs = []
        return "\n\n".join(paragraphs)

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
