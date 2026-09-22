"""Tests for CRUD service classes.

Services are tested in isolation: repositories and UnitOfWork are replaced
with lightweight stubs so the tests exercise only the service logic.
"""

from __future__ import annotations

import subprocess

import pytest

from dockb.exceptions import ChapterAfterNotFoundError, DuplicateTitleError
from dockb.infrastructure.document_store.store import DocumentMetadata, DocumentStore
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
    def __init__(self) -> None:
        super().__init__()
        self._document_of: dict[str, str] = {}
        self._index_of: dict[str, int] = {}

    def set_document(self, chapter_id: str, document_id: str) -> None:
        self._document_of[chapter_id] = document_id

    def set_index(self, chapter_id: str, index: int) -> None:
        self._index_of[chapter_id] = index

    def find_document_id(self, chapter_id: str) -> str | None:
        return self._document_of.get(chapter_id)

    def list_by_document(self, document_id: str) -> list[dict[str, str | int]]:
        _ = document_id
        return [{"id": m.id, "title": m.title, "index": self._index_of.get(m.id, 0)} for m in self._store.values()]

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


@pytest.fixture()
def doc_repo() -> StubDocumentRepo:
    return StubDocumentRepo()


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

    def test_create_rejects_exact_title_duplicate(self) -> None:
        existing = Document(id="d0", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d0"] = existing
        with pytest.raises(DuplicateTitleError):
            self.svc.create("d1", title="Faith", author="Paul")

    def test_create_accepts_distinct_title(self) -> None:
        existing = Document(id="d0", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d0"] = existing
        doc = self.svc.create("d1", title="Hope", author="Paul")
        assert doc.id == "d1"
        assert self.uow.committed

    def test_create_writes_document_metadata(self, tmp_path) -> None:
        store = DocumentStore(base_dir=tmp_path)
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store=store)
        svc.create("d1", title="Faith", author="Paul")
        assert store.read_metadata("d1") == DocumentMetadata(title="Faith", author="Paul")

    def test_create_without_store_skips_metadata(self) -> None:
        doc = self.svc.create("d1", title="Faith", author="Paul")
        assert doc.id == "d1"
        assert self.uow.committed

    def test_open_materializes_missing_tree(self, tmp_path, nlp) -> None:
        from dockb.models.token import Token

        chapter = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        para = Paragraph(id="p1", state=DataState.SYNC)
        sentence = Sentence(id="s1", state=DataState.SYNC)
        token = Token()
        token.set_text("Hello world.")
        sentence.tokens.append(token)
        para.sentences.append(sentence)
        chapter.paragraphs.append(para)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(chapter)
        self.repo._store["d1"] = doc

        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store=store, nlp=nlp)

        opened = svc.open("d1")

        assert opened is doc
        assert store.read_metadata("d1") == DocumentMetadata(title="Faith", author="Paul")
        assert store.chapter_exists("d1", "c1")
        content = store.read_chapter("d1", "c1")
        assert content is not None
        assert "Hello world." in content
        result = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout.strip()

    def test_open_does_not_overwrite_existing_tree(self, tmp_path, nlp) -> None:
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        store = DocumentStore(base_dir=tmp_path)
        store.write_metadata("d1", DocumentMetadata(title="Faith", author="Paul"))
        existing = store.chapter_file("d1", "c1")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("hand edit\n")
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store=store, nlp=nlp)

        svc.open("d1")

        assert store.read_chapter("d1", "c1") == "hand edit\n"

    def test_open_without_store_returns_document(self, nlp) -> None:
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store=None, nlp=nlp)
        assert svc.open("d1") is doc

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


class TestChapterService:  # pylint: disable=too-many-public-methods
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
        self.repo.set_index("c1", 2)
        result = self.svc.list_by_document("doc1")
        assert result == [{"id": "c1", "title": "Ch1", "index": 2}]

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
        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "0"}

    def test_create_without_after_places_first(self) -> None:
        self.svc.create("c1", title="Intro", document_id="d1", after_chapter_id=None)
        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "0"}

    def test_create_after_chapter_uses_next_index(self) -> None:
        first = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = first
        self.repo.set_index("c1", 0)

        self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="c1")

        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "1"}

    def test_create_after_middle_chapter_uses_next_index(self) -> None:
        self.repo._store["c1"] = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo.set_index("c1", 1)
        self.repo._store["c3"] = Chapter(id="c3", title="Ch3", state=DataState.SYNC)
        self.repo.set_index("c3", 2)

        self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="c1")

        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "2"}

    def test_create_after_unknown_chapter_raises(self) -> None:
        with pytest.raises(ChapterAfterNotFoundError):
            self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="ghost")

    def test_create_materializes_empty_chapter_file(self, tmp_path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_store=store)

        svc.create("c1", title="Intro", document_id="d1")

        content = store.read_chapter("d1", "c1")
        assert content is not None
        assert content.startswith("---")
        assert "id: c1" in content
        assert "title: Intro" in content
        assert "data-par-id" not in content

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

    def test_open_returns_none_when_missing(self) -> None:
        assert self.svc.open("nonexistent") is None

    def test_open_without_store_returns_chapter(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        assert self.svc.open("c1") is ch

    def test_open_materializes_missing_chapter_file(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_store=store, nlp=nlp)

        opened = svc.open("c1")

        assert opened is ch
        content = store.read_chapter("d1", "c1")
        assert content is not None
        assert content.startswith("---")
        assert "Intro" in content
        result = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout.strip()

    def test_open_does_not_overwrite_existing_chapter_file(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path)
        store.write_chapter("d1", "c1", "hand edit\n")
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_store=store, nlp=nlp)

        opened = svc.open("c1")

        assert opened is ch
        assert store.read_chapter("d1", "c1") == "hand edit\n"

    def test_open_without_document_skips_materialization(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_store=store, nlp=nlp)

        opened = svc.open("c1")

        assert opened is ch
        assert store.read_chapter("d1", "c1") is None

    def test_save_lock_shared_per_chapter(self) -> None:
        assert self.svc._save_lock("c1") is self.svc._save_lock("c1")
        assert self.svc._save_lock("c1") is not self.svc._save_lock("c2")

    def test_save_lock_evicts_when_idle(self) -> None:
        first = self.svc._save_lock("c1")
        self.svc._save_release("c1")
        assert "c1" not in self.svc._save_locks
        second = self.svc._save_lock("c1")
        assert second is not first
        self.svc._save_release("c1")

    def test_save_document_returns_none_when_missing(self) -> None:
        assert self.svc.save_document("nonexistent", "Hello") is None

    def test_save_document_returns_none_without_store(self, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_repo=doc_repo)
        assert svc.save_document("c1", "Hello") is None

    def test_save_document_returns_none_for_orphan(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=StubDocumentRepo(),
            document_store=store,
            nlp=nlp,
        )
        assert svc.save_document("c1", "Hello") is None

    def test_save_document_writes_force_identity_applies_and_snaps(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store=store,
            nlp=nlp,
        )

        result = svc.save_document("c1", "Hello there.\n\nSecond paragraph.")

        assert result is not None
        assert result.summary.created is False
        assert result.summary.added == 2
        assert "Hello there." in result.content
        assert "data-par-id" in result.content
        content = store.read_chapter("d1", "c1")
        assert content is not None
        assert "id: c1" in content
        assert "title: Intro" in content
        log = subprocess.run(["git", "log", "--format=%H"], cwd=str(tmp_path), capture_output=True, text=True, check=False)
        assert log.returncode == 0
        assert log.stdout.strip()

    def test_save_document_overwrites_conflicting_identity(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store=store,
            nlp=nlp,
        )

        result = svc.save_document(
            "c1",
            "---\nid: other-one\ntitle: Wrong\n---\nConflicting identity here.",
        )

        assert result is not None
        content = store.read_chapter("d1", "c1")
        assert content is not None
        assert "id: c1" in content
        assert "title: Intro" in content
        assert "id: other-one" not in content

    def test_save_document_absorbs_changed_paragraph(self, tmp_path, nlp, doc_repo) -> None:
        from dockb.models.token import Token

        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        para = Paragraph(id="p1", state=DataState.SYNC)
        sentence = Sentence(id="s1", state=DataState.SYNC)
        token = Token()
        token.set_text("Old text here.")
        sentence.tokens.append(token)
        para.sentences.append(sentence)
        ch.paragraphs.append(para)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store=store,
            nlp=nlp,
        )

        result = svc.save_document("c1", '<span data-par-id="p1">\nNew text here.\n</span>')

        assert result is not None
        assert result.summary.changed == 1
        assert "New text here." in result.content

    def test_open_document_returns_none_when_missing(self) -> None:
        assert self.svc.open_document("nonexistent") is None

    def test_open_document_returns_none_without_store(self, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_repo=doc_repo)
        assert svc.open_document("c1") is None

    def test_open_document_returns_none_for_orphan(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=StubDocumentRepo(),
            document_store=store,
            nlp=nlp,
        )
        assert svc.open_document("c1") is None

    def test_open_document_materializes_missing_file(self, tmp_path, nlp, doc_repo) -> None:
        from dockb.models.token import Token

        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        para = Paragraph(id="p1", state=DataState.SYNC)
        sentence = Sentence(id="s1", state=DataState.SYNC)
        token = Token()
        token.set_text("Hello world.")
        sentence.tokens.append(token)
        para.sentences.append(sentence)
        ch.paragraphs.append(para)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store=store,
            nlp=nlp,
        )

        content = svc.open_document("c1")

        assert content is not None
        assert "Hello world." in content
        assert content.startswith("---")
        log = subprocess.run(["git", "log", "--format=%H"], cwd=str(tmp_path), capture_output=True, text=True, check=False)
        assert log.returncode == 0
        assert log.stdout.strip()

    def test_open_document_absorbs_hand_edit(self, tmp_path, nlp, doc_repo) -> None:
        from dockb.models.token import Token

        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        para = Paragraph(id="p1", state=DataState.SYNC)
        sentence = Sentence(id="s1", state=DataState.SYNC)
        token = Token()
        token.set_text("Old text.")
        sentence.tokens.append(token)
        para.sentences.append(sentence)
        ch.paragraphs.append(para)
        doc = Document(id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
        store = DocumentStore(base_dir=tmp_path)
        store.write_chapter("d1", "c1", '---\nid: c1\ntitle: Intro\n---\n<span data-par-id="p1">\nEdited text.\n</span>\n')
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store=store,
            nlp=nlp,
        )

        content = svc.open_document("c1")

        assert content is not None
        assert "Edited text." in content
        log = subprocess.run(["git", "log", "--format=%H"], cwd=str(tmp_path), capture_output=True, text=True, check=False)
        assert log.returncode == 0
        assert log.stdout.strip()


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
