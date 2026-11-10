"""Tests for the per-document glossary service."""

from __future__ import annotations

from typing import Any

import pytest

from dockb.exceptions import DocumentNotFoundError
from dockb.services.glossary_service import GlossaryService, normalize_words


class _AccountStore:  # pylint: disable=too-few-public-methods
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], list[str]] = {}

    def get_glossary(self, username: str, document_id: str) -> list[str]:
        return list(self.rows.get((username, document_id), []))

    def set_glossary(self, username: str, document_id: str, words: list[str]) -> None:
        self.rows[(username, document_id)] = list(words)


class _DocumentRepo:  # pylint: disable=too-few-public-methods
    def __init__(self, owned: set[tuple[str, str]]) -> None:
        self.owned = owned
        self.calls: list[tuple[str, str]] = []

    def load_shell(self, document_id: str, owner: str) -> Any:
        self.calls.append((document_id, owner))
        return object() if (document_id, owner) in self.owned else None


class _ChapterRepo:  # pylint: disable=too-few-public-methods
    def __init__(self, names: dict[tuple[str, str], list[str]]) -> None:
        self.names = names
        self.calls: list[tuple[str, str]] = []

    def list_character_names(self, document_id: str, owner: str) -> list[str]:
        self.calls.append((document_id, owner))
        return list(self.names.get((document_id, owner), []))


def _service(
    *,
    owned: set[tuple[str, str]] | None = None,
    names: dict[tuple[str, str], list[str]] | None = None,
) -> tuple[GlossaryService, _AccountStore, _DocumentRepo, _ChapterRepo]:
    store = _AccountStore()
    documents = _DocumentRepo(owned if owned is not None else {("doc-1", "acct-1")})
    chapters = _ChapterRepo(names or {})
    return GlossaryService(store, documents, chapters), store, documents, chapters


def test_normalize_words_trims_blanks_and_case_insensitive_duplicates() -> None:
    assert normalize_words(["  Karakas ", "", "karakas", "teh", " TEH "]) == ["Karakas", "teh"]


class TestGetAndSet:
    def test_returns_the_stored_words(self) -> None:
        service, store, _, _ = _service()
        store.rows[("abby", "doc-1")] = ["Karakas"]

        assert service.get_words("doc-1", owner="acct-1", username="abby") == ["Karakas"]

    def test_set_stores_the_normalized_words_and_returns_them(self) -> None:
        service, store, _, _ = _service()

        saved = service.set_words("doc-1", [" Karakas ", "karakas", ""], owner="acct-1", username="abby")

        assert saved == ["Karakas"]
        assert store.rows[("abby", "doc-1")] == ["Karakas"]

    def test_a_document_the_account_does_not_own_is_absent_for_get(self) -> None:
        service, _, _, _ = _service(owned=set())

        with pytest.raises(DocumentNotFoundError):
            service.get_words("doc-1", owner="acct-1", username="abby")

    def test_a_document_the_account_does_not_own_is_absent_for_set(self) -> None:
        service, store, _, _ = _service(owned=set())

        with pytest.raises(DocumentNotFoundError):
            service.set_words("doc-1", ["word"], owner="acct-1", username="abby")
        assert not store.rows

    def test_ownership_is_checked_through_the_document_repo(self) -> None:
        service, _, documents, _ = _service()

        service.get_words("doc-1", owner="acct-1", username="abby")

        assert documents.calls == [("doc-1", "acct-1")]


class TestEffectiveWords:
    def test_merges_stored_words_and_character_names_without_case_duplicates(self) -> None:
        service, store, _, _ = _service(names={("doc-1", "acct-1"): ["Karakas", "Kiral"]})
        store.rows[("abby", "doc-1")] = ["teh", "karakas"]

        words = service.effective_words("doc-1", owner="acct-1", username="abby")

        assert words == ("teh", "karakas", "Kiral")

    def test_without_a_document_returns_nothing(self) -> None:
        service, _, documents, chapters = _service()

        assert not service.effective_words(None, owner="acct-1", username="abby")
        assert not documents.calls
        assert not chapters.calls

    def test_a_document_the_account_does_not_own_is_absent(self) -> None:
        service, _, _, _ = _service(owned=set())

        with pytest.raises(DocumentNotFoundError):
            service.effective_words("doc-1", owner="acct-1", username="abby")

    def test_character_names_are_read_for_the_same_owner(self) -> None:
        service, _, _, chapters = _service(names={("doc-1", "acct-1"): ["Karakas"]})

        service.effective_words("doc-1", owner="acct-1", username="abby")

        assert chapters.calls == [("doc-1", "acct-1")]
