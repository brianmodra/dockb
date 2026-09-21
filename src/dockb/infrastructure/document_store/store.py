"""Server-owned, id-keyed markdown file tree for the document lifecycle.

The backend owns the markdown chapter files and their per-document metadata,
arranged on disk under a single base directory (``DOCKB_CHAPTERS_DIR``):

.. code-block:: text

    <base>/
        <document_id>/
            document_metadata.yaml
            chapter-<chapter_id>.md

Paths are derived from ids only, and every id is validated so a hostile
document/chapter id cannot escape the base directory (``..``, separators,
absolute paths, control characters are all rejected).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

_METADATA_FILE = "document_metadata.yaml"
_CHAPTER_PREFIX = "chapter-"
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

    def document_dir(self, document_id: str) -> Path:
        """Return the directory owned by *document_id* (not created)."""
        self._validate(document_id, "document id")
        return self._base_dir / document_id

    def metadata_file(self, document_id: str) -> Path:
        """Return the metadata file path for *document_id*."""
        return self.document_dir(document_id) / _METADATA_FILE

    def chapter_file(self, document_id: str, chapter_id: str) -> Path:
        """Return the markdown file path for a chapter of *document_id*."""
        self._validate(document_id, "document id")
        self._validate(chapter_id, "chapter id")
        return self._base_dir / document_id / f"{_CHAPTER_PREFIX}{chapter_id}.md"

    def document_exists(self, document_id: str) -> bool:
        """Return whether the document's directory exists on disk."""
        return self.document_dir(document_id).is_dir()

    def chapter_exists(self, document_id: str, chapter_id: str) -> bool:
        """Return whether the chapter's markdown file exists on disk."""
        return self.chapter_file(document_id, chapter_id).is_file()

    def read_chapter(self, document_id: str, chapter_id: str) -> str | None:
        """Return a chapter file's raw content, or None when absent."""
        path = self.chapter_file(document_id, chapter_id)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def write_chapter(self, document_id: str, chapter_id: str, content: str) -> None:
        """Write *content* to a chapter file, creating the owning directory."""
        path = self.chapter_file(document_id, chapter_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read_metadata(self, document_id: str) -> DocumentMetadata | None:
        """Return a document's metadata, or None when absent."""
        path = self.metadata_file(document_id)
        if not path.is_file():
            return None
        attrs = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return DocumentMetadata(title=str(attrs.get("title") or ""), author=str(attrs.get("author") or ""))

    def write_metadata(self, document_id: str, metadata: DocumentMetadata) -> None:
        """Write *metadata*, preserving any other keys already in the file."""
        path = self.metadata_file(document_id)
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

    def list_chapter_files(self, document_id: str) -> list[Path]:
        """Return the chapter markdown files under *document_id*, sorted by name."""
        directory = self.document_dir(document_id)
        if not directory.is_dir():
            return []
        return sorted(path for path in directory.glob(f"{_CHAPTER_PREFIX}*.md") if path.is_file())

    @staticmethod
    def _validate(value: str, kind: str) -> None:
        """Reject an id that could escape the base directory."""
        if not value:
            raise ValueError(f"empty {kind} is not a valid id")
        if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value or "\n" in value:
            raise ValueError(f"{value!r} is not a valid id")
