"""Per-account DocumentStore construction from one shared base directory."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dockb.infrastructure.document_store.store import DocumentStore
from dockb.titles import validate_segment

_ENV_BASE_DIR = "DOCKB_CHAPTERS_DIR"


class DocumentStoreFactory:
    """Hand out one account's :class:`DocumentStore` at a time.

    Services hold the factory rather than a store, so the account a store belongs to
    is decided by the request that is being served instead of by whichever call site
    remembered to pass one. A store that spanned accounts would put every account's
    documents under the same directory and stage them into the same commit.

    The factory also owns the one piece of layout knowledge no store can hold: where a
    document's directory was *before* trees were per-account. A :class:`DocumentStore`
    is scoped to an account by construction — it cannot name ``<base>/<title>``, which
    is a path with no account segment at all — so the two operations on that older
    layout live here, where the base directory is already known.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)

    @classmethod
    def from_env(cls) -> DocumentStoreFactory:
        """Build a factory rooted at ``DOCKB_CHAPTERS_DIR`` (required)."""
        base = os.environ.get(_ENV_BASE_DIR)
        if not base:
            raise ValueError(f"{_ENV_BASE_DIR} must be set to the markdown tree base directory")
        return cls(Path(base))

    def for_account(self, account_id: str) -> DocumentStore:
        """Return the store for *account_id* — an internal account id, not a username."""
        return DocumentStore(base_dir=self._base_dir, account_id=account_id)

    def legacy_document_dir(self, document_title: str) -> Path:
        """Return ``<base>/<title>``, where a document's directory sat before accounts did.

        This is the layout a manuscript on disk has if it was imported before trees were
        per-account. The title is validated as a single path segment for the same reason
        it is everywhere else: the path is derived from a title, and a hostile title must
        not be able to name a directory outside the base.
        """
        validate_segment(document_title)
        return self._base_dir / document_title

    def remove_legacy_document(self, document_title: str) -> None:
        """Delete the pre-ownership directory ``<base>/<title>``. Absent is a no-op.

        The removal is deliberately not committed. The repository that lived at the base
        directory is the one per-account repositories replaced, and nothing reads it any
        more — the document is about to belong to an account, whose own repository holds
        the copy from now on. Committing a deletion into an abandoned repository would
        be bookkeeping for a reader that does not exist.

        A directory that cannot be removed raises, rather than being passed over. It is
        the document's only copy until the destination commits it, and an assignment that
        reported success while quietly leaving it behind would be a lie the next
        document with that title would pay for.
        """
        directory = self.legacy_document_dir(document_title)
        if directory.exists():
            shutil.rmtree(directory)
