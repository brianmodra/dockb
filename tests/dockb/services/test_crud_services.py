"""Tests for CRUD service classes.

Services are tested in isolation: repositories and UnitOfWork are replaced
with lightweight stubs so the tests exercise only the service logic.
"""

from __future__ import annotations

from dockb.models.base import DataState, DockbModel
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.crud_services import (
    ChapterService,
    DocumentService,
    ParagraphService,
    SentenceService,
)

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubRepo:
    """In-memory repository stub for testing services."""

    def __init__(self) -> None:
        self._store: dict[str, DockbModel] = {}

    def load(self, model_id: str) -> DockbModel | None:
        return self._store.get(model_id)

    def list_all(self) -> list[dict[str, str]]:
        return [{"id": m.id, "title": getattr(m, "title", ""), "author": getattr(m, "author", "")} for m in self._store.values()]

    def list_by_parent(self, _parent_id: str) -> list[dict[str, str]]:
        return [{"id": m.id} for m in self._store.values()]

    def save(self, model: DockbModel, **_parent_ids: str) -> None:
        self._store[model.id] = model


class StubDocumentRepo(StubRepo):
    def load(self, model_id: str) -> Document | None:
        return super().load(model_id)  # type: ignore[return-value]


class StubChapterRepo(StubRepo):
    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        return super().list_by_parent(document_id)

    def load(self, model_id: str) -> Chapter | None:
        return super().load(model_id)  # type: ignore[return-value]


class StubParagraphRepo(StubRepo):
    def list_by_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        return super().list_by_parent(chapter_id)

    def load(self, model_id: str) -> Paragraph | None:
        return super().load(model_id)  # type: ignore[return-value]


class StubSentenceRepo(StubRepo):
    def list_by_paragraph(self, paragraph_id: str) -> list[dict[str, str]]:
        return super().list_by_parent(paragraph_id)

    def load(self, model_id: str) -> Sentence | None:
        return super().load(model_id)  # type: ignore[return-value]


class StubUnitOfWork:
    """Captures registered models without touching Neo4j."""

    def __init__(self) -> None:
        self.registered: list[tuple[DockbModel, dict[str, str]]] = []
        self.committed = False

    def register(self, model: DockbModel, **parent_ids: str) -> None:
        self.registered.append((model, parent_ids))

    def commit(self) -> None:
        self.committed = True

    def flush_pending(self) -> None:
        self.committed = True


class StubUnitOfWorkFactory:  # pylint: disable=too-few-public-methods
    """Returns the same StubUnitOfWork every time."""

    def __init__(self, uow: StubUnitOfWork | None = None) -> None:
        self.uow = uow or StubUnitOfWork()

    def get_unit_of_work(self) -> StubUnitOfWork:
        return self.uow


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------


class TestDocumentService:
    def setup_method(self) -> None:
        self.repo = StubDocumentRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = DocumentService(uow_factory=self.factory, document_repo=self.repo)

    def test_list_all_empty(self) -> None:
        assert self.svc.list_all() == []

    def test_list_all_returns_summaries(self) -> None:
        doc = Document(id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.list_all()
        assert result == [{"id": "d1", "title": "T", "author": "A"}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent") is None

    def test_get_returns_document(self) -> None:
        doc = Document(id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.get("d1")
        assert result is doc

    def test_create_registers_new_document(self) -> None:
        doc = self.svc.create("d1", title="Faith", author="Paul")
        assert doc.id == "d1"
        assert doc.title == "Faith"
        assert doc.author == "Paul"
        assert doc.state == DataState.NEW
        assert self.uow.committed
        assert len(self.uow.registered) == 1
        assert self.uow.registered[0][0] is doc

    def test_create_document_no_parent_ids(self) -> None:
        self.svc.create("d1", title="T", author="A")
        assert self.uow.registered[0][1] == {}

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", "T", "A") is None

    def test_update_modifies_attrs(self) -> None:
        doc = Document(id="d1", title="Old", author="Old", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.update("d1", title="New", author="New")
        assert result is doc
        assert doc.title == "New"
        assert doc.author == "New"
        assert doc.state == DataState.CHANGED
        assert self.uow.committed

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent") is False

    def test_delete_sets_state(self) -> None:
        doc = Document(id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        assert self.svc.delete("d1") is True
        assert doc.state == DataState.DELETED
        assert self.uow.committed


# ---------------------------------------------------------------------------
# ChapterService
# ---------------------------------------------------------------------------


class TestChapterService:
    def setup_method(self) -> None:
        self.repo = StubChapterRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo)

    def test_list_by_document_empty(self) -> None:
        assert self.svc.list_by_document("doc1") == []

    def test_list_by_document_returns_summaries(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        result = self.svc.list_by_document("doc1")
        assert result == [{"id": "c1"}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent") is None

    def test_get_returns_chapter(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        assert self.svc.get("c1") is ch

    def test_create_registers_new_chapter(self) -> None:
        ch = self.svc.create("c1", title="Intro", document_id="d1")
        assert ch.id == "c1"
        assert ch.title == "Intro"
        assert ch.state == DataState.NEW
        assert self.uow.committed
        assert self.uow.registered[0][1] == {"document_id": "d1"}

    def test_update_modifies_title(self) -> None:
        ch = Chapter(id="c1", title="Old", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        result = self.svc.update("c1", title="New")
        assert result is ch
        assert ch.title == "New"
        assert ch.state == DataState.CHANGED

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", "T") is None

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent") is False

    def test_delete_sets_state(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        assert self.svc.delete("c1") is True
        assert ch.state == DataState.DELETED


# ---------------------------------------------------------------------------
# ParagraphService
# ---------------------------------------------------------------------------


class TestParagraphService:
    def setup_method(self) -> None:
        self.repo = StubParagraphRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = ParagraphService(uow_factory=self.factory, paragraph_repo=self.repo)

    def test_list_by_chapter_empty(self) -> None:
        assert self.svc.list_by_chapter("ch1") == []

    def test_list_by_chapter_returns_summaries(self) -> None:
        p = Paragraph(id="p1", state=DataState.SYNC)
        self.repo._store["p1"] = p
        result = self.svc.list_by_chapter("ch1")
        assert result == [{"id": "p1"}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent") is None

    def test_get_returns_paragraph(self) -> None:
        p = Paragraph(id="p1", state=DataState.SYNC)
        self.repo._store["p1"] = p
        assert self.svc.get("p1") is p

    def test_create_with_sentences(self) -> None:
        s1 = Sentence(id="s1", state=DataState.SYNC)
        p = self.svc.create("p1", content=[s1], chapter_id="ch1")
        assert p.id == "p1"
        assert p.state == DataState.NEW
        assert len(p.sentences) == 1
        assert self.uow.registered[0][1] == {"chapter_id": "ch1"}

    def test_update_replaces_sentences(self) -> None:
        s_old = Sentence(id="s_old", state=DataState.SYNC)
        p = Paragraph(id="p1", state=DataState.SYNC)
        p.append_child(s_old)
        self.repo._store["p1"] = p

        s_new = Sentence(id="s_new", state=DataState.NEW)
        result = self.svc.update("p1", content=[s_new], chapter_id="ch1")
        assert result is p
        assert len(p.sentences) == 1
        assert p.sentences[0].id == "s_new"
        assert p.state == DataState.CHANGED

    def test_update_preserves_existing_sentences(self) -> None:
        s1 = Sentence(id="s1", state=DataState.SYNC)
        p = Paragraph(id="p1", state=DataState.SYNC)
        p.append_child(s1)
        self.repo._store["p1"] = p

        # Same sentence comes back
        s1_again = Sentence(id="s1", state=DataState.SYNC)
        result = self.svc.update("p1", content=[s1_again], chapter_id="ch1")
        assert result is p
        assert len(p.sentences) == 1

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", [], chapter_id="ch1") is None

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent") is False

    def test_delete_sets_state(self) -> None:
        p = Paragraph(id="p1", state=DataState.SYNC)
        self.repo._store["p1"] = p
        assert self.svc.delete("p1") is True
        assert p.state == DataState.DELETED


# ---------------------------------------------------------------------------
# SentenceService
# ---------------------------------------------------------------------------


class TestSentenceService:
    def setup_method(self) -> None:
        self.repo = StubSentenceRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = SentenceService(uow_factory=self.factory, sentence_repo=self.repo)

    def test_list_by_paragraph_empty(self) -> None:
        assert self.svc.list_by_paragraph("p1") == []

    def test_list_by_paragraph_returns_summaries(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s
        result = self.svc.list_by_paragraph("p1")
        assert result == [{"id": "s1"}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent") is None

    def test_get_returns_sentence(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s
        assert self.svc.get("s1") is s

    def test_create_with_text(self) -> None:
        s = self.svc.create("s1", text="Hello", paragraph_id="p1")
        assert s.id == "s1"
        assert s.dirty
        assert self.uow.registered[0][1] == {"paragraph_id": "p1"}

    def test_update_replaces_text(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s

        result = self.svc.update("s1", text="new", paragraph_id="p1")
        assert result is s
        assert s.dirty

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", "", paragraph_id="p1") is None

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent") is False

    def test_delete_sets_state(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s
        assert self.svc.delete("s1") is True
        assert s.state == DataState.DELETED
