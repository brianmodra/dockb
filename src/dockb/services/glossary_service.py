"""Per-document proofreading glossary.

A glossary holds the words this document has accepted so the spelling checker stops
flagging them: invented names, dialect, and terms of art. It is stored in the account
SQLite file, keyed by the account username and the document id, because it is editor
state rather than manuscript content. The document's character names are not copied
into it; they are merged when a check runs, so renaming a character or editing their
name parts changes the accepted words without a migration.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dockb.exceptions import DocumentNotFoundError


def normalize_words(words: Iterable[str]) -> list[str]:
    """Return *words* trimmed, without blanks or case-insensitive duplicates."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in words:
        word = raw.strip()
        if not word:
            continue
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(word)
    return normalized


class GlossaryService:  # pylint: disable=too-few-public-methods
    """Reads and writes one document's accepted words, scoped to its owner."""

    def __init__(self, account_store: Any, document_repo: Any, chapter_repo: Any) -> None:
        self._account_store = account_store
        self._document_repo = document_repo
        self._chapter_repo = chapter_repo

    def get_words(self, document_id: str, *, owner: str, username: str) -> list[str]:
        """Return the stored glossary for *document_id*."""
        self._require_document(document_id, owner)
        return list(self._account_store.get_glossary(username, document_id))

    def set_words(self, document_id: str, words: Iterable[str], *, owner: str, username: str) -> list[str]:
        """Replace the stored glossary for *document_id* and return the saved words."""
        self._require_document(document_id, owner)
        normalized = normalize_words(words)
        self._account_store.set_glossary(username, document_id, normalized)
        return normalized

    def add_word(self, document_id: str, word: str, *, owner: str, username: str) -> list[str]:
        """Add one *word* to the glossary and return the saved words (idempotent)."""
        self._require_document(document_id, owner)
        normalized = normalize_words([*self._account_store.get_glossary(username, document_id), word])
        self._account_store.set_glossary(username, document_id, normalized)
        return normalized

    def remove_word(self, document_id: str, word: str, *, owner: str, username: str) -> list[str]:
        """Remove *word* (case-insensitively) and return the saved words; a no-op when absent."""
        self._require_document(document_id, owner)
        key = word.casefold()
        kept = [w for w in self._account_store.get_glossary(username, document_id) if w.casefold() != key]
        self._account_store.set_glossary(username, document_id, kept)
        return kept

    def effective_words(self, document_id: str | None, *, owner: str, username: str) -> tuple[str, ...]:
        """Return the stored glossary plus the document's character names."""
        if document_id is None:
            return ()
        self._require_document(document_id, owner)
        stored = self._account_store.get_glossary(username, document_id)
        names = self._chapter_repo.list_character_names(document_id, owner)
        return tuple(normalize_words([*stored, *names]))

    def _require_document(self, document_id: str, owner: str) -> None:
        if self._document_repo.load_shell(document_id, owner) is None:
            raise DocumentNotFoundError(document_id)
