"""Tests for CRUD service classes.

Services are tested in isolation: repositories and UnitOfWork are replaced
with lightweight stubs so the tests exercise only the service logic.
"""

from __future__ import annotations

# pylint: disable=too-many-lines
import subprocess
from pathlib import Path

import pytest

from dockb.exceptions import (
    ChapterAfterNotFoundError,
    ChapterCategoryMismatchError,
    DocumentOwnershipError,
    DuplicateTitleError,
)
from dockb.infrastructure.document_store import DocumentStore, DocumentStoreFactory
from dockb.infrastructure.document_store.store import DocumentMetadata
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
    """Document repository stub that honours ownership the way the real one does.

    A document owned by somebody else reads as absent rather than raising, so a test
    that forgets to pass an owner cannot accidentally pass by reading another
    account's document.
    """

    def __init__(self) -> None:
        super().__init__()
        self.forbid_full_load = False

    def _owned(self, model_id: str, owner: str) -> Document | None:
        model = self._store.get(model_id)
        if not isinstance(model, Document) or model.owner != owner:
            return None
        return model

    def load(self, model_id: str, owner: str) -> Document | None:  # type: ignore[override]  # pylint: disable=arguments-differ
        if self.forbid_full_load:
            raise AssertionError("full document load is forbidden on chapter paths")
        return self._owned(model_id, owner)

    def load_shell(self, model_id: str, owner: str) -> Document | None:  # type: ignore[override]
        model = self._owned(model_id, owner)
        if model is None:
            return None
        shell = Document(
            id=model.id,
            title=model.title,
            author=model.author,
            owner=model.owner,
            state=DataState.SYNC,
        )
        for chapter in model.chapters:
            shell.chapters.append(Chapter(id=chapter.id, state=DataState.SYNC))
        return shell

    def list_all(self, owner: str) -> list[dict[str, str]]:  # type: ignore[override]  # pylint: disable=arguments-differ
        return [
            {"id": m.id, "title": getattr(m, "title", ""), "author": getattr(m, "author", "")}
            for m in self._store.values()
            if isinstance(m, Document) and m.owner == owner
        ]

    def find_owner(self, model_id: str) -> str | None:
        model = self._store.get(model_id)
        return model.owner if isinstance(model, Document) and model.owner else None


class StubChapterRepo(StubRepo):
    def __init__(self) -> None:
        super().__init__()
        self._document_of: dict[str, str] = {}
        self._index_of: dict[str, int] = {}
        self._reorders: list[tuple[str, list[str]]] = []

    def set_document(self, chapter_id: str, document_id: str) -> None:
        self._document_of[chapter_id] = document_id

    def set_index(self, chapter_id: str, index: int) -> None:
        self._index_of[chapter_id] = index

    def find_document_id(self, chapter_id: str) -> str | None:
        return self._document_of.get(chapter_id)

    def list_by_document(self, document_id: str) -> list[dict[str, str | int]]:
        rows = [
            {
                "id": m.id,
                "title": m.title,
                "act": m.act,
                "category": m.category,
                "index": self._index_of.get(m.id, 0),
            }
            for m in self._store.values()
            if m.id not in self._document_of or self._document_of[m.id] == document_id
        ]
        rows.sort(key=lambda row: int(row["index"]))
        return rows

    def reorder(self, document_id: str, ordered_ids: list[str]) -> None:
        self._reorders.append((document_id, list(ordered_ids)))

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


@pytest.fixture()
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:  # pylint: disable=unused-argument
    """Give git a commit identity without a repository or the machine's own config.

    An account directory is its own repository, created on first use, so a test
    cannot pre-configure one with ``git config``. The environment variables apply to
    every repository git creates below, which keeps these tests independent of whether
    the machine running them has a global identity.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@test.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@test.com")


def read_file(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------


class TestDocumentService:  # pylint: disable=too-many-public-methods
    _OWNER = "acct-1"

    def setup_method(self) -> None:
        self.repo = StubDocumentRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = DocumentService(uow_factory=self.factory, document_repo=self.repo)

    def _store(self, tmp_path) -> DocumentStore:
        return DocumentStore(base_dir=tmp_path, account_id=self._OWNER)

    def _service_with_store(self, tmp_path, nlp=None) -> DocumentService:
        """A service whose filesystem is this account's tree, and nobody else's."""
        return DocumentService(
            uow_factory=self.factory,
            document_repo=self.repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

    def test_list_all_empty(self) -> None:
        assert self.svc.list_all(self._OWNER) == []

    def test_list_all_returns_summaries(self) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.list_all(self._OWNER)
        assert result == [{"id": "d1", "title": "T", "author": "A"}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent", self._OWNER) is None

    def test_get_returns_document(self) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.get("d1", self._OWNER)
        assert result is doc

    def test_create_registers_new_document(self) -> None:
        doc = self.svc.create("d1", title="Faith", author="Paul", owner=self._OWNER)
        assert doc.id == "d1"
        assert doc.title == "Faith"
        assert doc.author == "Paul"
        assert doc.state == DataState.NEW
        assert self.uow.committed
        assert len(self.uow.registered) == 1
        assert self.uow.registered[0][0] is doc

    def test_create_document_no_parent_ids(self) -> None:
        self.svc.create("d1", title="T", author="A", owner=self._OWNER)
        assert self.uow.registered[0][1] == {}

    def test_create_rejects_exact_title_duplicate(self) -> None:
        existing = Document(owner=self._OWNER, id="d0", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d0"] = existing
        with pytest.raises(DuplicateTitleError):
            self.svc.create("d1", title="Faith", author="Paul", owner=self._OWNER)

    def test_create_rejects_case_insensitive_title_duplicate(self) -> None:
        existing = Document(owner=self._OWNER, id="d0", title="Linchpin", author="Paul", state=DataState.SYNC)
        self.repo._store["d0"] = existing
        with pytest.raises(DuplicateTitleError):
            self.svc.create("d1", title="linchPIN", author="Paul", owner=self._OWNER)

    def test_create_accepts_distinct_title(self) -> None:
        existing = Document(owner=self._OWNER, id="d0", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d0"] = existing
        doc = self.svc.create("d1", title="Hope", author="Paul", owner=self._OWNER)
        assert doc.id == "d1"
        assert self.uow.committed

    def test_two_accounts_may_each_hold_the_same_title(self) -> None:
        """A title is free in one account precisely because another account holds it."""
        self.svc.create("d1", title="Faith", author="Paul", owner=self._OWNER)
        other = DocumentService(uow_factory=self.factory, document_repo=self.repo)
        second = other.create("d2", title="Faith", author="Paul", owner="acct-2")

        assert second.owner == "acct-2"
        assert [model.owner for model, _ in self.uow.registered] == [self._OWNER, "acct-2"]

    def test_create_writes_document_metadata(self, tmp_path) -> None:
        store = self._store(tmp_path)
        svc = self._service_with_store(tmp_path)
        svc.create("d1", title="Faith", author="Paul", owner=self._OWNER)
        assert store.read_metadata("Faith") == DocumentMetadata(title="Faith", author="Paul")

    def test_create_without_store_skips_metadata(self) -> None:
        doc = self.svc.create("d1", title="Faith", author="Paul", owner=self._OWNER)
        assert doc.id == "d1"
        assert self.uow.committed

    def test_create_rejects_a_blank_owner(self) -> None:
        """A document with no account has nowhere to keep its manuscript.

        It must be refused before the graph is touched: committing the node first and
        failing on the filesystem would leave a document no account can reach, with no
        tree -- exactly the stranded state the backfill command exists to repair.
        """
        with pytest.raises(DocumentOwnershipError):
            self.svc.create("d1", title="Faith", author="Paul", owner="")

        assert not self.uow.committed
        assert not self.uow.registered

    def test_create_rejects_a_whitespace_owner(self) -> None:
        with pytest.raises(DocumentOwnershipError):
            self.svc.create("d1", title="Faith", author="Paul", owner="   ")

        assert not self.uow.committed

    def test_create_rejects_a_blank_owner_before_a_store_is_touched(self, tmp_path) -> None:
        store = self._store(tmp_path)
        svc = self._service_with_store(tmp_path)

        with pytest.raises(DocumentOwnershipError):
            svc.create("d1", title="Faith", author="Paul", owner="")

        assert not store.document_exists("Faith")
        assert not list(tmp_path.iterdir())

    def test_create_rejects_a_blank_owner_even_without_a_store(self) -> None:
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store_factory=None)

        with pytest.raises(DocumentOwnershipError):
            svc.create("d1", title="Faith", author="Paul", owner="")

        assert not self.uow.committed

    def test_open_returns_none_for_an_unowned_document(self) -> None:
        """Ownership is required to read, not merely to write."""
        doc = Document(owner="", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc

        assert self.svc.open("d1", self._OWNER) is None

    def test_open_returns_none_for_another_accounts_document(self) -> None:
        doc = Document(owner="acct-2", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc

        assert self.svc.open("d1", self._OWNER) is None

    def test_open_writes_nothing_for_another_accounts_document(self, tmp_path) -> None:
        doc = Document(owner="acct-2", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        store = self._store(tmp_path)
        svc = self._service_with_store(tmp_path)

        assert svc.open("d1", self._OWNER) is None
        assert not store.document_exists("Faith")
        assert not list(tmp_path.iterdir())

    def test_update_returns_none_for_another_accounts_document(self) -> None:
        doc = Document(owner="acct-2", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc

        assert self.svc.update("d1", title="Hijacked", author="Mallory", owner=self._OWNER) is None
        assert doc.title == "Faith"
        assert not self.uow.committed

    def test_delete_returns_false_for_another_accounts_document(self) -> None:
        doc = Document(owner="acct-2", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc

        assert self.svc.delete("d1", self._OWNER) is False
        assert doc.state == DataState.SYNC
        assert not self.uow.committed

    def test_delete_leaves_another_accounts_tree_alone(self, tmp_path) -> None:
        other = DocumentStore(base_dir=tmp_path, account_id="acct-2")
        other.write_metadata("Faith", DocumentMetadata(title="Faith", author="Paul"))
        doc = Document(owner="acct-2", id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = self._service_with_store(tmp_path)

        assert svc.delete("d1", self._OWNER) is False
        assert other.document_exists("Faith")

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
        doc = Document(owner=self._OWNER, id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        doc.chapters.append(chapter)
        self.repo._store["d1"] = doc

        store = self._store(tmp_path)
        svc = self._service_with_store(tmp_path, nlp)

        opened = svc.open("d1", self._OWNER)

        assert opened is doc
        assert store.read_metadata("Faith") == DocumentMetadata(title="Faith", author="Paul")
        assert store.chapter_exists("Faith", "", "Intro")
        content = store.read_chapter("Faith", "", "Intro")
        assert content is not None
        assert "Hello world." in content
        result = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(store.account_dir()),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout.strip()

    def test_open_does_not_overwrite_existing_tree(self, tmp_path, nlp) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        store = self._store(tmp_path)
        store.write_metadata("Faith", DocumentMetadata(title="Faith", author="Paul"))
        existing = store.chapter_file("Faith", "", "Intro")
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("hand edit\n")
        svc = self._service_with_store(tmp_path, nlp)

        svc.open("d1", self._OWNER)

        assert store.read_chapter("Faith", "", "Intro") == "hand edit\n"

    def test_open_without_store_returns_document(self, nlp) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="Faith", author="Paul", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = DocumentService(uow_factory=self.factory, document_repo=self.repo, document_store_factory=None, nlp=nlp)
        assert svc.open("d1", self._OWNER) is doc

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", "T", "A", self._OWNER) is None

    def test_update_modifies_attrs(self) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="Old", author="Old", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        result = self.svc.update("d1", title="New", author="New", owner=self._OWNER)
        assert result is doc
        assert doc.title == "New"
        assert doc.author == "New"
        assert doc.state == DataState.CHANGED
        assert self.uow.committed

    def test_update_rejects_title_taken_by_another_document(self) -> None:
        self.repo._store["d1"] = Document(owner=self._OWNER, id="d1", title="Alpha", author="A", state=DataState.SYNC)
        self.repo._store["d2"] = Document(owner=self._OWNER, id="d2", title="Beta", author="B", state=DataState.SYNC)
        with pytest.raises(DuplicateTitleError):
            self.svc.update("d2", title="ALPHA", author="B", owner=self._OWNER)

    def test_update_allows_title_case_change_of_own(self) -> None:
        self.repo._store["d1"] = Document(owner=self._OWNER, id="d1", title="Alpha", author="A", state=DataState.SYNC)
        result = self.svc.update("d1", title="alpha", author="A", owner=self._OWNER)
        assert result is not None
        assert result.title == "alpha"

    def test_update_renames_store_tree_when_title_changes(self, tmp_path) -> None:

        def git_status() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(tmp_path), capture_output=True, text=True, check=False
            ).stdout.strip()

        store = self._store(tmp_path)
        store.write_metadata("T", DocumentMetadata(title="T", author="A"))
        store.write_chapter("T", "Act I", "Opening 1", "# body\n")
        store.git_commit("T", "materialize: doc")
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = self._service_with_store(tmp_path)

        result = svc.update("d1", title="New", author="B", owner=self._OWNER)

        assert result is doc
        assert not store.document_exists("T")
        assert store.document_exists("New")
        assert store.read_metadata("New") == DocumentMetadata(title="New", author="B")
        assert store.chapter_exists("New", "Act I", "Opening 1")
        assert git_status() == ""

    def test_update_author_only_writes_metadata(self, tmp_path) -> None:

        def git_status() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(tmp_path), capture_output=True, text=True, check=False
            ).stdout.strip()

        store = self._store(tmp_path)
        store.write_metadata("T", DocumentMetadata(title="T", author="A"))
        store.git_commit("T", "materialize: doc")
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = self._service_with_store(tmp_path)

        result = svc.update("d1", title="T", author="B", owner=self._OWNER)

        assert result is doc
        assert store.document_exists("T")
        assert store.read_metadata("T") == DocumentMetadata(title="T", author="B")
        assert git_status() == ""

    def test_open_refreshes_metadata_from_graph(self, tmp_path) -> None:
        store = self._store(tmp_path)
        store.write_metadata("T", DocumentMetadata(title="T", author="stale"))
        store.git_commit("T", "materialize: doc")
        doc = Document(owner=self._OWNER, id="d1", title="T", author="fresh", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = self._service_with_store(tmp_path)

        assert svc.open("d1", self._OWNER) is doc
        assert store.read_metadata("T") == DocumentMetadata(title="T", author="fresh")

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent", self._OWNER) is False

    def test_delete_sets_state(self) -> None:
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        assert self.svc.delete("d1", self._OWNER) is True
        assert doc.state == DataState.DELETED
        assert self.uow.committed

    def test_delete_removes_store_tree_first(self, tmp_path) -> None:

        def git_status() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(tmp_path), capture_output=True, text=True, check=False
            ).stdout.strip()

        store = self._store(tmp_path)
        store.write_metadata("T", DocumentMetadata(title="T", author="A"))
        doc = Document(owner=self._OWNER, id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        svc = self._service_with_store(tmp_path)
        assert svc.delete("d1", self._OWNER) is True
        assert not store.document_exists("T")
        assert doc.state == DataState.DELETED
        assert self.uow.committed
        assert git_status() == ""


# ---------------------------------------------------------------------------
# ChapterService
# ---------------------------------------------------------------------------


class TestChapterService:  # pylint: disable=too-many-public-methods,too-many-locals
    _OWNER = "acct-1"

    def setup_method(self) -> None:
        self.repo = StubChapterRepo()
        self.doc_repo = StubDocumentRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=self.doc_repo,
        )

    def _store(self, tmp_path) -> DocumentStore:
        """The store for the account under test -- the only tree this class may write."""
        return DocumentStore(base_dir=tmp_path, account_id=self._OWNER)

    def _service_with_store(self, tmp_path, nlp=None, doc_repo=None) -> ChapterService:
        return ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo if doc_repo is not None else self.doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

    def _own_document(self, document_id: str = "d1", title: str = "Faith") -> Document:
        """Register a document owned by this class's account, as a chapter needs one."""
        doc = Document(id=document_id, title=title, author="Paul", owner=self._OWNER, state=DataState.SYNC)
        self.doc_repo._store[document_id] = doc
        self.repo.set_document(next((ch.id for ch in self.repo._store.values()), ""), document_id)
        return doc

    def test_create_registers_new_chapter(self) -> None:
        self._own_document()
        ch = self.svc.create("c1", title="Intro", document_id="d1", owner=self._OWNER)
        assert ch.id == "c1"
        assert ch.title == "Intro"
        assert ch.state == DataState.NEW
        assert self.uow.committed
        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "0"}

    def test_list_by_document_empty(self) -> None:
        assert self.svc.list_by_document("doc1") == []

    def test_list_by_document_returns_summaries(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_index("c1", 2)
        result = self.svc.list_by_document("doc1")
        assert result == [{"id": "c1", "title": "Ch1", "act": "", "category": "Chapter", "index": 2}]

    def test_get_returns_none_when_missing(self) -> None:
        assert self.svc.get("nonexistent") is None

    def test_get_returns_chapter(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        assert self.svc.get("c1") is ch

    def test_create_defaults_category_chapter(self) -> None:
        self._own_document()
        ch = self.svc.create("c1", title="Intro", document_id="d1", owner=self._OWNER)
        assert ch.category == "Chapter"

    def test_create_with_category_sets_category_on_chapter(self) -> None:
        self._own_document()
        ch = self.svc.create("c1", title="Intro", document_id="d1", category="Character", owner=self._OWNER)
        assert ch.category == "Character"

    def test_create_without_after_places_first(self) -> None:
        self._own_document()
        self.svc.create("c1", title="Intro", document_id="d1", after_chapter_id=None, owner=self._OWNER)
        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "0"}

    def test_create_after_chapter_uses_next_index(self) -> None:
        self._own_document()
        first = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = first
        self.repo.set_index("c1", 0)

        self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="c1", owner=self._OWNER)

        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "1"}

    def test_create_after_middle_chapter_uses_next_index(self) -> None:
        self._own_document()
        self.repo._store["c1"] = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo.set_index("c1", 1)
        self.repo._store["c3"] = Chapter(id="c3", title="Ch3", state=DataState.SYNC)
        self.repo.set_index("c3", 2)

        self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="c1", owner=self._OWNER)

        assert self.uow.registered[0][1] == {"document_id": "d1", "index": "2"}

    def test_create_after_unknown_chapter_raises(self) -> None:
        self._own_document()
        with pytest.raises(ChapterAfterNotFoundError):
            self.svc.create("c2", title="Ch2", document_id="d1", after_chapter_id="ghost", owner=self._OWNER)

    def test_create_rejects_case_insensitive_duplicate_title_in_document(self) -> None:
        self._own_document()
        self.repo._store["c1"] = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo.set_document("c1", "d1")
        with pytest.raises(DuplicateTitleError):
            self.svc.create("c2", title="INTRO", document_id="d1", owner=self._OWNER)

    def test_create_allows_same_title_in_other_document(self) -> None:
        self._own_document("d1")
        self._own_document("d2")
        self.repo._store["c1"] = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo.set_document("c1", "d1")
        ch = self.svc.create("c2", title="Intro", document_id="d2", owner=self._OWNER)
        assert ch.id == "c2"

    def test_create_materializes_empty_chapter_file(self, tmp_path, doc_repo) -> None:
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )

        svc.create("c1", title="Intro", document_id="d1", owner=self._OWNER)

        content = store.read_chapter("Faith", "", "Intro")
        assert content is not None
        assert content.startswith("---")
        assert "id: c1" in content
        assert "title: Intro" in content
        assert "data-par-id" not in content

    def test_create_materializes_character_chapter_under_characters_dir(self, tmp_path, doc_repo) -> None:
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )

        svc.create("c1", title="Dramatis", document_id="d1", category="Character", owner=self._OWNER)

        assert store.chapter_file("Faith", "", "Dramatis", category="Character").is_file()
        content = store.read_chapter("Faith", "", "Dramatis", category="Character")
        assert content is not None
        assert "category: Character" in content

    def test_update_modifies_title(self) -> None:
        ch = Chapter(id="c1", title="Old", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        result = self.svc.update("c1", title="New", owner=self._OWNER)
        assert result is ch
        assert ch.title == "New"
        assert ch.state == DataState.CHANGED

    def test_update_renames_store_file_when_title_changes(self, tmp_path) -> None:

        def git_status() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(store.account_dir()), capture_output=True, text=True, check=False
            ).stdout.strip()

        ch = Chapter(id="c1", title="Old", act="Act I", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo = StubDocumentRepo()
        doc_repo._store["d1"] = Document(id="d1", title="T", author="A", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("T", "Act I", "Old", "---\ntitle: Old\n---\n\n# body\n")
        store.git_commit("T", "materialize: doc")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )

        result = svc.update("c1", title="New", owner=self._OWNER)

        assert result is ch
        assert ch.title == "New"
        assert ch.state == DataState.CHANGED
        assert not store.chapter_exists("T", "Act I", "Old")
        content = store.read_chapter("T", "Act I", "New")
        assert content is not None
        assert "title: New" in content
        assert git_status() == ""

    def test_update_rejects_duplicate_title_in_document(self) -> None:
        self.repo._store["c1"] = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo.set_document("c1", "d1")
        self.repo._store["c2"] = Chapter(id="c2", title="Body", state=DataState.SYNC)
        self.repo.set_document("c2", "d1")
        with pytest.raises(DuplicateTitleError):
            self.svc.update("c2", title="intro", owner=self._OWNER)

    def test_update_allows_same_title_in_other_document(self) -> None:
        self.repo._store["c1"] = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo.set_document("c1", "d1")
        self.repo._store["c2"] = Chapter(id="c2", title="Intro", state=DataState.SYNC)
        self.repo.set_document("c2", "d2")
        result = self.svc.update("c2", title="Intro", owner=self._OWNER)
        assert result is not None
        assert result.title == "Intro"

    def test_update_returns_none_when_missing(self) -> None:
        assert self.svc.update("nonexistent", "T", self._OWNER) is None

    def test_delete_returns_false_when_missing(self) -> None:
        assert self.svc.delete("nonexistent", self._OWNER) is False

    def test_delete_sets_state(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        assert self.svc.delete("c1", self._OWNER) is True
        assert ch.state == DataState.DELETED

    def test_delete_removes_store_file_when_document_resolved(self, tmp_path) -> None:

        def git_status() -> str:
            return subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(store.account_dir()), capture_output=True, text=True, check=False
            ).stdout.strip()

        ch = Chapter(id="c1", title="Ch1", act="Act I", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo = StubDocumentRepo()
        doc_repo._store["d1"] = Document(id="d1", title="T", author="A", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("T", "Act I", "Ch1", "# body\n")
        store.git_commit("T", "materialize: doc")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )
        svc.delete("c1", self._OWNER)
        assert not store.chapter_exists("T", "Act I", "Ch1")
        assert ch.state == DataState.DELETED
        assert self.uow.committed
        assert git_status() == ""

    def test_delete_without_store_still_marks_deleted(self) -> None:
        self.repo.set_document("c1", "d1")
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.svc.delete("c1", self._OWNER)
        assert ch.state == DataState.DELETED

    def _git_store(self, tmp_path) -> DocumentStore:
        return DocumentStore(base_dir=tmp_path, account_id=self._OWNER)

    def test_open_uses_shell_load(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc_repo.forbid_full_load = True
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("Faith", "", "Intro", "hand edit\n")
        svc = self._service_with_store(tmp_path, nlp=nlp)

        assert svc.open("c1", self._OWNER) is ch

    def test_open_document_uses_shell_load(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        doc_repo.forbid_full_load = True
        store = self._git_store(tmp_path)
        store.write_chapter("Faith", "", "Intro", '---\nid: c1\ntitle: Intro\n---\n\n<span data-par-id="p1">\nEdited.\n</span>\n')
        svc = self._service_with_store(tmp_path, nlp=nlp, doc_repo=doc_repo)

        content = svc.open_document("c1", self._OWNER)

        assert content is not None
        assert "Edited." in content

    def test_save_document_uses_shell_load(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        doc_repo.forbid_full_load = True
        store = self._git_store(tmp_path)
        store.write_chapter("Faith", "", "Intro", '---\nid: c1\ntitle: Intro\n---\n\n<span data-par-id="p1">\nEdited.\n</span>\n')
        svc = self._service_with_store(tmp_path, nlp=nlp, doc_repo=doc_repo)

        result = svc.save_document("c1", '<span data-par-id="p1">\nSaved.\n</span>', self._OWNER)

        assert result is not None
        assert "Saved." in result.content

    def test_create_uses_shell_load(self, tmp_path, nlp, doc_repo) -> None:
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc_repo.forbid_full_load = True
        store = self._git_store(tmp_path)
        svc = self._service_with_store(tmp_path, nlp=nlp, doc_repo=doc_repo)

        svc.create("c1", title="Intro", document_id="d1", owner=self._OWNER)

        assert store.read_chapter("Faith", "", "Intro") is not None

    def test_update_uses_shell_load(self, tmp_path, doc_repo) -> None:
        ch = Chapter(id="c1", title="Old", act="Act I", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="T", author="A", owner=self._OWNER, state=DataState.SYNC)
        doc_repo.forbid_full_load = True
        store = self._git_store(tmp_path)
        store.write_chapter("T", "Act I", "Old", "---\ntitle: Old\n---\n\n# body\n")
        store.git_commit("T", "materialize: doc")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )

        result = svc.update("c1", title="New", owner=self._OWNER)

        assert result is ch
        assert ch.title == "New"

    def test_delete_uses_shell_load(self, tmp_path, doc_repo) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="T", author="A", owner=self._OWNER, state=DataState.SYNC)
        doc_repo.forbid_full_load = True
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
        )

        svc.delete("c1", self._OWNER)

    def test_move_returns_none_when_missing(self) -> None:
        assert self.svc.move("nonexistent", after_chapter_id=None) is None

    def test_move_returns_none_when_orphaned(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        assert self.svc.move("c1", after_chapter_id=None) is None

    def test_move_after_itself_is_noop(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        result = self.svc.move("c1", after_chapter_id="c1")
        assert result is ch
        assert not self.repo._reorders

    def test_move_first_orders_chapter_at_head(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", state=DataState.SYNC)
        for ch in (c1, c2):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, list((c1, c2)).index(ch))

        self.svc.move("c2", after_chapter_id=None)

        assert self.repo._reorders == [("d1", ["c2", "c1"])]

    def test_move_after_chapter_uses_new_order(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", state=DataState.SYNC)
        c3 = Chapter(id="c3", title="Ch3", state=DataState.SYNC)
        for ch in (c1, c2, c3):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, list((c1, c2, c3)).index(ch))

        self.svc.move("c3", after_chapter_id="c1")

        assert self.repo._reorders == [("d1", ["c1", "c3", "c2"])]

    def test_move_after_unknown_chapter_raises(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        with pytest.raises(ChapterAfterNotFoundError):
            self.svc.move("c1", after_chapter_id="ghost")
        assert not self.repo._reorders

    def test_move_after_chapter_adopts_predecessor_act(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", act="Act I", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", act="Act II", state=DataState.SYNC)
        c3 = Chapter(id="c3", title="Ch3", act="Act III", state=DataState.SYNC)
        for ch in (c1, c2, c3):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, list((c1, c2, c3)).index(ch))

        self.svc.move("c3", after_chapter_id="c1")

        assert c3.act == "Act I"
        assert c3.state == DataState.CHANGED
        assert c1.act == "Act I"
        assert c2.act == "Act II"
        assert self.uow.registered and self.uow.registered[0][0] is c3
        assert self.uow.committed
        assert self.repo._reorders == [("d1", ["c1", "c3", "c2"])]

    def test_move_first_adopts_old_first_chapter_act(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", act="Act I", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", act="Act II", state=DataState.SYNC)
        for ch in (c1, c2):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, list((c1, c2)).index(ch))

        self.svc.move("c2", after_chapter_id=None)

        assert c2.act == "Act I"
        assert c1.act == "Act I"
        assert self.uow.committed
        assert self.repo._reorders == [("d1", ["c2", "c1"])]

    def test_move_overwrites_act_even_to_empty(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", act="", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", act="Act II", state=DataState.SYNC)
        for ch in (c1, c2):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
        self.repo.set_index("c1", 1)
        self.repo.set_index("c2", 0)

        self.svc.move("c2", after_chapter_id="c1")

        assert c2.act == ""
        assert self.uow.committed
        assert self.repo._reorders == [("d1", ["c1", "c2"])]

    def test_move_does_not_register_act_when_order_unchanged(self) -> None:
        c1 = Chapter(id="c1", title="Ch1", act="Act I", state=DataState.SYNC)
        c2 = Chapter(id="c2", title="Ch2", act="", state=DataState.SYNC)
        for ch in (c1, c2):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, list((c1, c2)).index(ch))

        self.svc.move("c1", after_chapter_id=None)

        assert c1.act == "Act I"
        assert c2.act == ""
        assert not self.uow.registered
        assert not self.uow.committed
        assert self.repo._reorders == [("d1", ["c1", "c2"])]

    def test_move_rejects_landing_in_other_category(self) -> None:
        chapter = Chapter(id="c1", title="Ch1", act="Act I", category="Chapter", state=DataState.SYNC)
        character = Chapter(id="char", title="Dramatis", category="Character", state=DataState.SYNC)
        for ch, index in ((chapter, 0), (character, 1)):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, index)

        with pytest.raises(ChapterCategoryMismatchError):
            self.svc.move("char", after_chapter_id="c1")

        assert not self.repo._reorders
        assert character.act == ""
        assert character.category == "Character"

    def test_move_first_rejects_other_category(self) -> None:
        chapter = Chapter(id="c1", title="Ch1", act="Act I", category="Chapter", state=DataState.SYNC)
        character = Chapter(id="char", title="Dramatis", category="Character", state=DataState.SYNC)
        for ch, index in ((chapter, 0), (character, 1)):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, index)

        with pytest.raises(ChapterCategoryMismatchError):
            self.svc.move("char", after_chapter_id=None)

        assert not self.repo._reorders

    def test_move_within_category_still_reorders(self) -> None:
        first = Chapter(id="a", title="A", category="Character", state=DataState.SYNC)
        second = Chapter(id="b", title="B", category="Character", state=DataState.SYNC)
        for ch, index in ((first, 0), (second, 1)):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, index)

        self.svc.move("b", after_chapter_id=None)

        assert self.repo._reorders == [("d1", ["b", "a"])]

    def test_move_to_front_of_own_block_keeps_act(self) -> None:
        chapter = Chapter(id="c1", title="Ch1", act="Act I", category="Chapter", state=DataState.SYNC)
        first = Chapter(id="a", title="A", category="Character", state=DataState.SYNC)
        second = Chapter(id="b", title="B", category="Character", state=DataState.SYNC)
        for ch, index in ((chapter, 0), (first, 1), (second, 2)):
            self.repo._store[ch.id] = ch
            self.repo.set_document(ch.id, "d1")
            self.repo.set_index(ch.id, index)

        self.svc.move("b", after_chapter_id="c1")

        assert self.repo._reorders == [("d1", ["c1", "b", "a"])]
        assert second.act == ""
        assert second.category == "Character"
        assert not self.uow.committed

    def test_open_returns_none_when_missing(self) -> None:
        assert self.svc.open("nonexistent", self._OWNER) is None

    def test_open_without_store_returns_chapter(self) -> None:
        ch = Chapter(id="c1", title="Ch1", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        assert self.svc.open("c1", self._OWNER) is ch

    def test_open_materializes_missing_chapter_file(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        opened = svc.open("c1", self._OWNER)

        assert opened is ch
        content = store.read_chapter("Faith", "", "Intro")
        assert content is not None
        assert content.startswith("---")
        assert "Intro" in content
        result = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(store.account_dir()),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert result.stdout.strip()

    def test_open_materializes_character_chapter_under_characters_dir(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Dramatis", category="Character", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        opened = svc.open("c1", self._OWNER)

        assert opened is ch
        content = store.read_chapter("Faith", "", "Dramatis", category="Character")
        assert content is not None

    def test_open_does_not_overwrite_existing_chapter_file(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        doc_repo._store["d1"] = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("Faith", "", "Intro", "hand edit\n")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        opened = svc.open("c1", self._OWNER)

        assert opened is ch
        assert store.read_chapter("Faith", "", "Intro") == "hand edit\n"

    def test_open_without_document_skips_materialization(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        opened = svc.open("c1", self._OWNER)

        assert opened is ch
        assert store.read_chapter("Faith", "", "Intro") is None

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
        assert self.svc.save_document("nonexistent", "Hello", self._OWNER) is None

    def test_save_document_returns_none_without_store(self, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_repo=doc_repo)
        assert svc.save_document("c1", "Hello", self._OWNER) is None

    def test_save_document_returns_none_for_orphan(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=StubDocumentRepo(),
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )
        assert svc.save_document("c1", "Hello", self._OWNER) is None

    def test_save_document_writes_force_identity_applies_and_snaps(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        result = svc.save_document("c1", "Hello there.\n\nSecond paragraph.", self._OWNER)

        assert result is not None
        assert result.summary.created is False
        assert result.summary.added == 2
        assert "Hello there." in result.content
        assert "data-par-id" in result.content
        content = store.read_chapter("Faith", "", "Intro")
        assert content is not None
        assert "id: c1" in content
        assert "title: Intro" in content
        log = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(store.account_dir()),
            capture_output=True,
            text=True,
            check=False,
        )
        assert log.returncode == 0
        assert log.stdout.strip()

    def test_save_document_forces_act_into_front_matter(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", act="Act I", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        svc.save_document("c1", "Body text.", self._OWNER)

        content = read_file(store.chapter_file("Faith", "Act I", "Intro"))
        assert "act: Act I" in content

    def test_save_document_does_not_force_empty_act(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        svc.save_document("c1", "Body text.", self._OWNER)

        content = read_file(store.chapter_file("Faith", "", "Intro"))
        assert "act" not in content

    def test_save_document_overwrites_conflicting_identity(self, tmp_path, nlp, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        result = svc.save_document(
            "c1",
            "---\nid: other-one\ntitle: Wrong\n---\nConflicting identity here.",
            self._OWNER,
        )

        assert result is not None
        content = store.read_chapter("Faith", "", "Intro")
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
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        result = svc.save_document("c1", '<span data-par-id="p1">\nNew text here.\n</span>', self._OWNER)

        assert result is not None
        assert result.summary.changed == 1
        assert "New text here." in result.content

    def test_open_document_returns_none_when_missing(self) -> None:
        assert self.svc.open_document("nonexistent", self._OWNER) is None

    def test_open_document_returns_none_without_store(self, doc_repo) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo, document_repo=doc_repo)
        assert svc.open_document("c1", self._OWNER) is None

    def test_open_document_returns_none_for_orphan(self, tmp_path, nlp) -> None:
        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=StubDocumentRepo(),
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )
        assert svc.open_document("c1", self._OWNER) is None

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
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        content = svc.open_document("c1", self._OWNER)

        assert content is not None
        assert "Hello world." in content
        assert content.startswith("---")
        log = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(store.account_dir()),
            capture_output=True,
            text=True,
            check=False,
        )
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
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("Faith", "", "Intro", '---\nid: c1\ntitle: Intro\n---\n<span data-par-id="p1">\nEdited text.\n</span>\n')
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        content = svc.open_document("c1", self._OWNER)

        assert content is not None
        assert "Edited text." in content
        log = subprocess.run(
            ["git", "log", "--format=%H"],
            cwd=str(store.account_dir()),
            capture_output=True,
            text=True,
            check=False,
        )
        assert log.returncode == 0
        assert log.stdout.strip()

    def test_open_document_records_stage_timings(self, tmp_path, nlp, doc_repo) -> None:
        from dockb.models.token import Token
        from dockb.timing import trace

        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        para = Paragraph(id="p1", state=DataState.SYNC)
        sentence = Sentence(id="s1", state=DataState.SYNC)
        token = Token()
        token.set_text("Old text.")
        sentence.tokens.append(token)
        para.sentences.append(sentence)
        ch.paragraphs.append(para)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        store = DocumentStore(base_dir=tmp_path, account_id=self._OWNER)
        store.write_chapter("Faith", "", "Intro", '---\nid: c1\ntitle: Intro\n---\n<span data-par-id="p1">\nEdited text.\n</span>\n')
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        with trace() as timings:
            content = svc.open_document("c1", self._OWNER)

        assert content is not None
        names = [part.split(" ")[0] for part in timings.summary().split(", ")]
        assert names == [
            "repo.chapter.load",
            "repo.chapter.find_document_id",
            "repo.document.load",
            "stage.apply_chapter_file",
            "stage.parse_file",
            "stage.spacy",
            "stage.persist",
            "stage.render",
            "stage.git_commit",
            "stage.read_chapter",
        ]

    def test_open_document_records_materialize_stage(self, tmp_path, nlp, doc_repo) -> None:
        from dockb.timing import trace

        ch = Chapter(id="c1", title="Intro", state=DataState.SYNC)
        doc = Document(id="d1", title="Faith", author="Paul", owner=self._OWNER, state=DataState.SYNC)
        doc.chapters.append(ch)
        doc_repo._store["d1"] = doc
        self.repo._store["c1"] = ch
        self.repo.set_document("c1", "d1")
        svc = ChapterService(
            uow_factory=self.factory,
            chapter_repo=self.repo,
            document_repo=doc_repo,
            document_store_factory=DocumentStoreFactory(base_dir=tmp_path),
            nlp=nlp,
        )

        with trace() as timings:
            content = svc.open_document("c1", self._OWNER)

        assert content is not None
        names = [part.split(" ")[0] for part in timings.summary().split(", ")]
        assert names == [
            "repo.chapter.load",
            "repo.chapter.find_document_id",
            "repo.document.load",
            "stage.materialize",
            "stage.read_chapter",
        ]


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
        self.svc.delete("nonexistent")

    def test_delete_sets_state(self) -> None:
        p = Paragraph(id="p1", state=DataState.SYNC)
        self.repo._store["p1"] = p
        self.svc.delete("p1")
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
        self.svc.delete("nonexistent")

    def test_delete_sets_state(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s
        self.svc.delete("s1")
        assert s.state == DataState.DELETED
