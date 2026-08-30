"""Parse a markdown snapshot back into model objects."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from dockb.exceptions import SnapshotError
from dockb.models.chapter import Chapter
from dockb.models.paragraph import Paragraph


class SnapshotReader:
    """Read chapter snapshots from markdown files (optionally at a specific git commit)."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

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
        front_matter, body = self._split_front_matter(content)
        attrs = yaml.safe_load(front_matter) or {}

        chapter_id_from_file = attrs.pop("id", chapter_id)
        title = attrs.pop("title", "")
        extras = attrs

        chapter = Chapter(id=chapter_id_from_file, title=title)
        chapter._snapshot_extras = extras  # pylint: disable=protected-access

        paragraphs_text = body.strip().split("\n\n") if body.strip() else []
        for para_text in paragraphs_text:
            paragraph = Paragraph()
            paragraph.set_text(para_text.strip())
            chapter.paragraphs.append(paragraph)

        return chapter

    def _split_front_matter(self, content: str) -> tuple[str, str]:
        if not content.startswith("---"):
            raise SnapshotError("Snapshot file does not start with YAML front matter")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise SnapshotError("Snapshot file is missing closing '---' for front matter")

        return parts[1], parts[2]

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
