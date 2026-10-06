"""Server-owned, account/act-keyed markdown file tree for the document lifecycle.

The backend owns the markdown chapter files and their per-document metadata,
arranged on disk under a single base directory (``DOCKB_CHAPTERS_DIR``). Each
account has its own directory and its own git repository, so commits and history
never span accounts:

.. code-block:: text

    <base>/
        <account_id>/
            .git/
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
control characters are all rejected). The account directory is named by an
internal account id rather than a username, and that id is validated as a single
path segment for the same reason titles are.
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
from dockb.titles import is_unsafe_segment, validate_segment

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
    """Resolve and read/write one account's markdown tree under a base dir.

    Scoped to a single account: there is no way to build a store that spans accounts,
    because a document's directory lives under the owner's account directory and git
    commands run inside that account's own repository.

    *account_id* names that directory, so it is held to the same single-segment rule
    as a title. An account id is minted by the accounts store rather than typed by a
    user, which is why nothing needs to normalize one — but the store is where paths
    are built, so it is where an id that is not a segment is refused.
    """

    def __init__(self, base_dir: Path, account_id: str) -> None:
        if not account_id or not account_id.strip():
            raise ValueError("account_id is required: a document store is scoped to one account")
        if is_unsafe_segment(account_id):
            raise ValueError(f"{account_id!r} is not a valid account id")
        self._base_dir = Path(base_dir)
        self._account_id = account_id

    @classmethod
    def from_env(cls, account_id: str) -> DocumentStore:
        """Build a store rooted at ``DOCKB_CHAPTERS_DIR`` (required) for *account_id*."""
        base = os.environ.get(_ENV_BASE_DIR)
        if not base:
            raise ValueError(f"{_ENV_BASE_DIR} must be set to the markdown tree base directory")
        return cls(Path(base), account_id)

    @property
    def account_id(self) -> str:
        """The account this store is scoped to, for scoping reads to that account."""
        return self._account_id

    def account_dir(self) -> Path:
        """Return the directory holding *account_id*'s repositories and documents (not created)."""
        return self._base_dir / self._account_id

    def document_dir(self, document_title: str) -> Path:
        """Return the directory owned by *document_title* (not created)."""
        self._validate_title(document_title)
        return self.account_dir() / document_title

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
        """Commit the document's directory to the account's own git repository.

        Each account directory is its own repository, so a commit can only ever
        contain one account's documents; nothing stages across accounts even if a
        title were to collide. Only files under *document_title* are staged. When the
        document has nothing new to commit — even if unrelated untracked files (e.g.
        runtime state) exist elsewhere in the account's tree — the call is a no-op.

        A document with no directory on disk is likewise a no-op, which is what
        ``remove_document``/``rename_document`` already do for an absent document:
        "not on disk" means nothing to do, not a failure. The title is still
        validated, so an unsafe title raises here as it does everywhere else.
        """
        directory = self.document_dir(document_title)
        if not directory.is_dir():
            return
        self._ensure_repo()
        try:
            self._git("add", "--", document_title)
        except SnapshotError as exc:
            if "not a git repository" in str(exc):
                raise SnapshotError(f"{self.account_dir()} is not a git repository; the document store owns the repo") from exc
            raise
        changed = self._git("status", "--porcelain", "--", document_title)
        if not changed.strip():
            return
        self._git("commit", "-m", message)

    def adopt_document(self, document_title: str, source: Path) -> None:
        """Copy a document's directory from *source* into this account's tree and commit it.

        This is how a document that belonged to somebody else, or to nobody, arrives in
        this account's tree: the files are copied rather than moved so a failure part way
        through leaves the original where it was, and the copy is committed here so it is
        this account's history from its first commit — history does not travel between
        repositories, and stitching it across with ``format-patch`` would buy a tree that
        only ever held one account's work.

        Refuses to write over an existing directory rather than merging into it: two
        documents' files under one directory is a manuscript neither account wrote, and
        the graph would refuse the same assignment anyway. A *source* that is not a
        directory is a no-op, because there is nothing to adopt and the document's content
        is in the graph regardless — the editor materializes the tree on first open.
        """
        self._validate_title(document_title)
        if not source.is_dir():
            return
        directory = self.document_dir(document_title)
        if directory.exists():
            raise SnapshotError(f"cannot adopt {document_title!r}: {directory} already exists")
        shutil.copytree(source, directory)
        self.git_commit(document_title, f"adopt: {document_title}")

    def remove_document(self, document_title: str) -> None:
        """Remove a document's owned directory from disk and git.

        The whole directory is deleted — tracked files via ``git rm`` plus any
        untracked files on disk — and the removal is committed. A document that
        does not exist on disk is a no-op.
        """
        directory = self.document_dir(document_title)
        if not directory.is_dir():
            return
        self._ensure_repo()
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
        self._ensure_repo()
        try:
            self._git("rm", "-f", "--", str(path.relative_to(self.account_dir())))
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
        self._ensure_repo()
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
        self._ensure_repo()
        self._git(
            "mv",
            "--",
            str(old_path.relative_to(self.account_dir())),
            str(new_path.relative_to(self.account_dir())),
        )
        content = self.read_chapter(document_title, act, new_title, category)
        if content is not None:
            self.write_chapter(document_title, act, new_title, front_matter.merge(content, {"title": new_title}), category)
        self.git_commit(document_title, f"rename: chapter {old_title} -> {new_title}")

    def _ensure_repo(self) -> None:
        """Make sure the account directory exists and is a git repository.

        Each account's documents live in their own repository so a commit cannot span
        accounts. That repository is created on first use rather than at startup: which
        accounts exist is a runtime fact, and an account that never writes a document
        never needs a directory. ``.git`` is checked with the filesystem rather than
        ``git rev-parse`` so the common case costs no subprocess.
        """
        account_dir = self.account_dir()
        if (account_dir / ".git").is_dir():
            return
        account_dir.mkdir(parents=True, exist_ok=True)
        self._git("init")

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.account_dir()),
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
        validate_segment(value)
