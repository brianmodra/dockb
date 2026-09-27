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
            Characters/
                <chapter_title>.md

Chapters without an act live under ``Act None``; an act is a directory named
``Act <name>`` (the verbatim chapter ``act`` when it is already prefixed).
``Character`` chapters always live under the reserved ``Characters``
directory whatever their act.
Paths are derived from titles only, and every title is validated so a hostile
title cannot escape the base directory (``..``, separators, absolute paths,
control characters are all rejected).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from dockb.exceptions import SnapshotError
from dockb.infrastructure.markdown import front_matter

_METADATA_FILE = "document_metadata.yaml"
_ACT_NONE = "Act None"
_ACT_PREFIX = "Act "
_CHARACTERS_DIR = "Characters"
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

    def chapter_file(
        self,
        document_title: str,
        act: str,
        chapter_title: str,
        category: str = "Chapter",
    ) -> Path:
        """Return the markdown file path for a chapter of *document_title*.

        A ``Character`` chapter lives under the reserved ``Characters``
        directory, whatever its act; any other category resolves through the
        act directory (empty act → ``Act None``).
        """
        self._validate_title(chapter_title)
        directory_name = self._chapter_dir_name(act, category)
        self._validate_title(directory_name)
        return self.document_dir(document_title) / directory_name / f"{chapter_title}.md"

    def document_exists(self, document_title: str) -> bool:
        """Return whether the document's directory exists on disk."""
        return self.document_dir(document_title).is_dir()

    def chapter_exists(
        self,
        document_title: str,
        act: str,
        chapter_title: str,
        category: str = "Chapter",
    ) -> bool:
        """Return whether the chapter's markdown file exists on disk."""
        return self.chapter_file(document_title, act, chapter_title, category).is_file()

    def read_chapter(
        self,
        document_title: str,
        act: str,
        chapter_title: str,
        category: str = "Chapter",
    ) -> str | None:
        """Return a chapter file's raw content, or None when absent."""
        path = self.chapter_file(document_title, act, chapter_title, category)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def write_chapter(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        document_title: str,
        act: str,
        chapter_title: str,
        content: str,
        category: str = "Chapter",
    ) -> None:
        """Write *content* to a chapter file, creating the owning directories."""
        path = self.chapter_file(document_title, act, chapter_title, category)
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

    def remove_document(self, document_title: str) -> None:
        """Remove a document's owned directory from disk and git.

        The whole directory is deleted — tracked files via ``git rm`` plus any
        untracked files on disk — and the removal is committed. A document that
        does not exist on disk is a no-op.
        """
        directory = self.document_dir(document_title)
        if not directory.is_dir():
            return
        try:
            self._git("rm", "-r", "-f", "--", document_title)
        except SnapshotError as exc:
            if "did not match any files" not in str(exc):
                raise
        shutil.rmtree(directory, ignore_errors=True)
        if self._git("status", "--porcelain", "--", document_title).strip():
            self._git("commit", "-m", f"remove: {document_title}")

    def remove_chapter(
        self,
        document_title: str,
        act: str,
        chapter_title: str,
        category: str = "Chapter",
    ) -> None:
        """Remove a chapter's markdown file and prune emptied directories.

        The file is staged for removal via ``git rm`` and deleted from disk, and
        the removal is committed. An act, ``Characters``, or document directory
        left empty by the removal is deleted too, so ``document_exists`` stays
        accurate. A chapter with no file on disk is a no-op.
        """
        path = self.chapter_file(document_title, act, chapter_title, category)
        if not path.is_file():
            return
        try:
            self._git("rm", "-f", "--", str(path.relative_to(self._base_dir)))
        except SnapshotError as exc:
            if "did not match any files" not in str(exc):
                raise
        path.unlink(missing_ok=True)
        if self._git("status", "--porcelain", "--", document_title).strip():
            self._git("commit", "-m", f"remove: chapter {chapter_title}")
        try:
            path.parent.rmdir()
        except OSError:
            return
        try:
            path.parent.parent.rmdir()
        except OSError:
            return

    def rename_document(self, old_title: str, new_title: str) -> None:
        """git mv a document's owned directory to *new_title* and commit.

        The metadata file inside is rewritten with the new title — author and
        any other keys are preserved. A directory that does not exist on disk
        is a no-op; renaming onto an existing directory raises.
        """
        old_dir = self.document_dir(old_title)
        if not old_dir.is_dir() or old_title == new_title:
            return
        new_dir = self.document_dir(new_title)
        if new_dir.exists():
            raise SnapshotError(f"cannot rename {old_title!r}: {new_title!r} already exists")
        self._git("mv", "--", old_title, new_title)
        metadata = self.read_metadata(new_title)
        if metadata is not None:
            self.write_metadata(new_title, DocumentMetadata(title=new_title, author=metadata.author))
        self.git_commit(new_title, f"rename: {old_title} -> {new_title}")

    def rename_chapter(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        document_title: str,
        act: str,
        old_title: str,
        new_title: str,
        category: str = "Chapter",
    ) -> None:
        """git mv a chapter's markdown file to *new_title* and commit.

        The front matter title inside the moved file is rewritten to match. A
        file that does not exist on disk is a no-op; renaming onto an existing
        file raises.
        """
        old_path = self.chapter_file(document_title, act, old_title, category)
        if not old_path.is_file() or old_title == new_title:
            return
        new_path = self.chapter_file(document_title, act, new_title, category)
        if new_path.exists():
            raise SnapshotError(f"cannot rename chapter {old_title!r}: {new_title!r} already exists")
        self._git(
            "mv",
            "--",
            str(old_path.relative_to(self._base_dir)),
            str(new_path.relative_to(self._base_dir)),
        )
        content = self.read_chapter(document_title, act, new_title, category)
        if content is not None:
            self.write_chapter(document_title, act, new_title, front_matter.merge(content, {"title": new_title}), category)
        self.git_commit(document_title, f"rename: chapter {old_title} -> {new_title}")

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

    @classmethod
    def _chapter_dir_name(cls, act: str, category: str) -> str:
        """Return the on-disk chapter directory for an *act*/*category* pair.

        A ``Character`` chapter always lives under the reserved ``Characters``
        directory (never an act directory); any other category — the only
        values ever written, and never a free-form path — resolves through
        ``_act_dir_name``.
        """
        if category == "Character":
            return _CHARACTERS_DIR
        return cls._act_dir_name(act)

    @staticmethod
    def _validate_title(value: str) -> None:
        """Reject a title that could escape the base directory."""
        if not value:
            raise ValueError("empty title is not a valid title")
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError(f"{value!r} is not a valid title")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f"{value!r} is not a valid title")
