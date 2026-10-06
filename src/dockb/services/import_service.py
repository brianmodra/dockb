"""Import an uploaded document directory into the knowledge graph.

The HTTP upload arrives as a set of named parts, which the server cannot trust
as paths and would not want to keep on disk. This service turns those parts
into a temporary document directory, runs the existing directory walker over
it, and deletes it — so the same import the shell command performs works
without a caller ever naming a path the server can read.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from starlette.concurrency import run_in_threadpool

from dockb.exceptions import DocumentOwnershipError
from dockb.services.markdown_import import ChapterImportSummary, import_document_directory
from dockb.uploads import (
    MAX_FILE_COUNT,
    MAX_TOTAL_BYTES,
    UploadBudget,
    UploadRejectedError,
    UploadTooLargeError,
    document_root,
    resolve_inside,
    validate_part_path,
)

if TYPE_CHECKING:
    from spacy.language import Language

    from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
    from dockb.repositories.chapter_repository import ChapterRepository
    from dockb.repositories.document_repository import DocumentRepository

# Large enough that a chunk read is one syscall for a normal chapter file, and
# small enough that the cap is enforced long before memory is a concern.
_CHUNK_BYTES = 64 * 1024


class UploadedPart(Protocol):
    """The part of an ``UploadFile`` this service needs."""

    @property
    def filename(self) -> str | None:
        """The caller-chosen name, which is untrusted input."""

    async def read(self, size: int = -1) -> bytes:
        """Read the next *size* bytes, or the rest when *size* is negative."""


class ImportService:  # pylint: disable=too-few-public-methods
    """Import a multipart upload as a document directory."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        nlp: Language,
        document_repo: DocumentRepository,
        chapter_repo: ChapterRepository,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._nlp = nlp
        self._document_repo = document_repo
        self._chapter_repo = chapter_repo
        self._uow_factory = uow_factory

    async def import_parts(
        self,
        parts: list[Any],
        user_name: str,
        *,
        owner: str,
        single_newline_paragraphs: bool = False,
    ) -> list[ChapterImportSummary]:
        """Import *parts* as one document directory.

        *owner* is the account id the document belongs to, and *user_name* is the
        caller's username, which the document's own metadata records as its author.
        They are kept apart because they answer different questions: ownership is what
        every later read is scoped by, and a username is mutable provider data that a
        reader sees.

        Every part's name is validated before a single byte is written, so a
        rejected upload never touches the disk. Each part is then streamed into
        a temporary directory, which is deleted whether the import succeeds or
        fails. Write-back is off: the uploaded bytes belong to the caller, and
        the canonical form is written by the editor, not by an upload.

        Raises ``DocumentOwnershipError`` when there is no account to own the document:
        a document created for nobody would be invisible to every account and
        reachable only through the admin CLI that assigns it, which is not what an
        upload asked for.
        """
        if not owner.strip():
            raise DocumentOwnershipError("an import needs the account the document belongs to")
        if len(parts) > MAX_FILE_COUNT:
            raise UploadTooLargeError(f"too many files: an upload is limited to {MAX_FILE_COUNT} files")
        names = [validate_part_path(part.filename) for part in parts]
        document_dir = document_root(names)

        # The shared root is kept in the staged layout, because the directory's
        # own name is what the walker takes as the document's default title.
        temp_dir = Path(tempfile.mkdtemp(prefix="dockb-import-"))
        budget = UploadBudget(MAX_TOTAL_BYTES)
        try:
            try:
                for part, relative in zip(parts, names, strict=True):
                    destination = resolve_inside(temp_dir, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    await self._write_part(part, destination, budget)
            except (FileExistsError, NotADirectoryError, IsADirectoryError) as exc:
                # One part's path can be another's directory, or collide with
                # it; the filesystem answers that as one of these three. What it
                # means is that the upload does not describe a tree, which is
                # the caller's mistake to be told about, not a fault of ours.
                # Other OSErrors — a full disk, a read-only mount — are ours and
                # are left to surface as a server fault.
                raise UploadRejectedError(f"the upload's files do not form a directory tree: {exc}") from exc
            return await run_in_threadpool(
                import_document_directory,
                temp_dir / document_dir,
                user_name,
                self._nlp,
                self._document_repo,
                self._chapter_repo,
                self._uow_factory,
                single_newline_paragraphs=single_newline_paragraphs,
                write_back=False,
                owner=owner,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    async def _write_part(part: UploadedPart, destination: Path, budget: UploadBudget) -> None:
        """Stream one part to *destination*, drawing on the upload's shared budget.

        The size is counted as the bytes arrive rather than measured first, so an
        oversized upload is abandoned partway instead of being buffered whole.
        The budget is shared across parts so the cap applies to the upload as a
        whole, not to each file in it.
        """
        with destination.open("wb") as handle:
            while True:
                chunk = await part.read(_CHUNK_BYTES)
                if not chunk:
                    break
                budget.charge(len(chunk))
                handle.write(chunk)
