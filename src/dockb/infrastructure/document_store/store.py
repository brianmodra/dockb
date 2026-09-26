"""Server-owned, title/act-keyed markdown file tree for the document lifecycle.

The backend owns the markdown chapter files and their per-document metadata,
arranged on disk under a single base directory (``DOCKB_CHAPTERS_DIR``):

.. code-block:: text

    <base>/
        <document_title>/
            document_metadata.yaml
            Act I/
                <chapter_title>.md
            Act None/
                <chapter_title>.md

Chapters without an act live under ``Act None``; an act is a directory named
``Act <name>`` (the verbatim chapter ``act`` when it is already prefixed).
Paths are derived from titles only, and every title is validated so a hostile
title cannot escape the base directory (``..``, separators, absolute paths,
control characters are all rejected).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from dockb.exceptions import SnapshotError

_METADATA_FILE = "document_metadata.yaml"
_ACT_NONE = "Act None"
_ACT_PREFIX = "Act "
_ENV_BASE_DIR = "DOCKB_CHAPTERS_DIR"


@dataclass
class DocumentMetadata:
    """A document's on-disk title and author."""

    title: str
    author: str


class DocumentStore:
    """Resolve and read/write the server-owned markdown tree under a base dir."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)

    @classmethod
    def from_env(cls) -> DocumentStore:
        """Build a store rooted at ``DOCKB_CHAPTERS_DIR`` (required)."""
        base = os.environ.get(_ENV_BASE_DIR)
        if not base:
            raise ValueError(f"{_ENV_BASE_DIR} must be set to the markdown tree base directory")
        return cls(Path(base))

    def document_dir(self, document_title: str) -> Path:
        """Return the directory owned by *document_title* (not created)."""
        self._validate_title(document_title)
        return self._base_dir / document_title

    def act_dir(self, document_title: str, act: str) -> Path:
        """Return the per-act chapter directory for a chapter of *document_title*."""
        act_name = self._act_dir_name(act)
        self._validate_title(act_name)
        return self.document_dir(document_title) / act_name

    def metadata_file(self, document_title: str) -> Path:
        """Return the metadata file path for *document_title*."""
        return self.document_dir(document_title) / _METADATA_FILE

    def chapter_file(self, document_title: str, act: str, chapter_title: str) -> Path:
        """Return the markdown file path for a chapter of *document_title*."""
        self._validate_title(chapter_title)
        return self.act_dir(document_title, act) / f"{chapter_title}.md"

    def document_exists(self, document_title: str) -> bool:
        """Return whether the document's directory exists on disk."""
        return self.document_dir(document_title).is_dir()

    def chapter_exists(self, document_title: str, act: str, chapter_title: str) -> bool:
        """Return whether the chapter's markdown file exists on disk."""
        return self.chapter_file(document_title, act, chapter_title).is_file()

    def read_chapter(self, document_title: str, act: str, chapter_title: str) -> str | None:
        """Return a chapter file's raw content, or None when absent."""
        path = self.chapter_file(document_title, act, chapter_title)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def write_chapter(self, document_title: str, act: str, chapter_title: str, content: str) -> None:
        """Write *content* to a chapter file, creating the owning directories."""
        path = self.chapter_file(document_title, act, chapter_title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_metadata(self, document_title: str) -> DocumentMetadata | None:
        """Return a document's metadata, or None when absent."""
        path = self.metadata_file(document_title)
        if not path.is_file():
            return None
        attrs = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return DocumentMetadata(title=str(attrs.get("title") or ""), author=str(attrs.get("author") or ""))

    def write_metadata(self, document_title: str, metadata: DocumentMetadata) -> None:
        """Write *metadata*, preserving any other keys already in the file."""
        path = self.metadata_file(document_title)
        attrs: dict[str, object] = {}
        if path.is_file():
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                attrs = dict(parsed)
        attrs["title"] = metadata.title
        attrs["author"] = metadata.author
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(attrs, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def list_chapter_files(self, document_title: str) -> list[Path]:
        """Return the chapter markdown files under *document_title*, sorted by path."""
        directory = self.document_dir(document_title)
        if not directory.is_dir():
            return []
        return sorted(path for path in directory.rglob("*.md") if path.is_file())

    def git_commit(self, document_title: str, message: str) -> None:
        """Commit the document's directory to the git repo rooted at the base dir.

        The base directory must be a git repository (as SnapshotWriter expects);
        only files under *document_title* are staged. When the document has nothing
        new to commit — even if unrelated untracked files (e.g. runtime state)
        exist elsewhere in the tree — the call is a no-op.
        """
        self.document_dir(document_title)
        try:
            self._git("add", "--", document_title)
        except SnapshotError as exc:
            if "not a git repository" in str(exc):
                raise SnapshotError(f"{self._base_dir} is not a git repository; the document store owns the repo") from exc
            raise
        changed = self._git("status", "--porcelain", "--", document_title)
        if not changed.strip():
            return
        self._git("commit", "-m", message)

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

    @classmethod
    def _act_dir_name(cls, act: str) -> str:
        """Return the on-disk act directory name for a chapter's *act*.

        An empty act maps to the reserved ``Act None`` directory; an act that
        is not already ``Act ``-prefixed gets the prefix applied.
        """
        act = act.strip()
        if not act:
            return _ACT_NONE
        if act.startswith(_ACT_PREFIX):
            return act
        return f"{_ACT_PREFIX}{act}"

    @staticmethod
    def _validate_title(value: str) -> None:
        """Reject a title that could escape the base directory."""
        if not value:
            raise ValueError("empty title is not a valid title")
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError(f"{value!r} is not a valid title")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f"{value!r} is not a valid title")
