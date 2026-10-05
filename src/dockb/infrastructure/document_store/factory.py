"""Per-account DocumentStore construction from one shared base directory."""

from __future__ import annotations

import os
from pathlib import Path

from dockb.infrastructure.document_store.store import DocumentStore

_ENV_BASE_DIR = "DOCKB_CHAPTERS_DIR"


class DocumentStoreFactory:
    """Hand out one account's :class:`DocumentStore` at a time.

    Services hold the factory rather than a store, so the account a store belongs to
    is decided by the request that is being served instead of by whichever call site
    remembered to pass one. A store that spanned accounts would put every account's
    documents under the same directory and stage them into the same commit.
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
