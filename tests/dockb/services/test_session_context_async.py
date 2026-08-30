"""Tests for SessionContext enhancements and async service integration.

WP5 adds JobQueue and DocCache to SessionContext, and makes paragraph/sentence
services use async job creation (DeleteJob + ReconstructJob + CommitJob) when
content is provided.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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
from dockb.services.semantics.commit_job import CommitJob
from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.job import Job
from dockb.services.semantics.reconstruct_job import ReconstructJob
from dockb.services.session_context import SessionContext

# ---------------------------------------------------------------------------
# Stubs / Spies
# ---------------------------------------------------------------------------


class SpyJobQueue:
    """Captures enqueued jobs without running them."""

    def __init__(self) -> None:
        self.enqueued: list[Job] = []

    def enqueue(self, job: Job) -> None:
        self.enqueued.append(job)

    def cancel_job(self, _job: Job) -> bool:
        return False


class StubRepo:
    """In-memory repository stub."""

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
# SessionContext with JobQueue and DocCache
# ---------------------------------------------------------------------------


class TestSessionContextEnhancements:
    """Verify SessionContext bundles JobQueue and DocCache."""

    def test_holds_job_queue(self) -> None:
        jq = SpyJobQueue()
        ctx = SessionContext(job_queue=jq)  # type: ignore[arg-type]
        assert ctx.job_queue is jq

    def test_holds_doc_cache(self) -> None:
        dc = MagicMock()
        ctx = SessionContext(doc_cache=dc)
        assert ctx.doc_cache is dc

    def test_pending_notifications_still_works(self) -> None:
        ctx = SessionContext()
        ctx.add_notification({"type": "sentence_split", "paragraph_id": "p1"})
        pending = ctx.pending_notifications()
        assert len(pending) == 1
        assert not ctx.pending_notifications()


# ---------------------------------------------------------------------------
# DocumentService — sync only, no async jobs
# ---------------------------------------------------------------------------


class TestDocumentServiceNoAsync:
    """Document operations never enqueue async jobs."""

    def setup_method(self) -> None:
        self.repo = StubDocumentRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = DocumentService(uow_factory=self.factory, document_repo=self.repo)

    def test_create_does_not_enqueue_jobs(self) -> None:
        self.svc.create("d1", title="T", author="A")
        assert self.uow.committed

    def test_update_does_not_enqueue_jobs(self) -> None:
        doc = Document(id="d1", title="Old", author="Old", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        self.svc.update("d1", title="New", author="New")
        assert self.uow.committed

    def test_delete_does_not_enqueue_jobs(self) -> None:
        doc = Document(id="d1", title="T", author="A", state=DataState.SYNC)
        self.repo._store["d1"] = doc
        self.svc.delete("d1")
        assert self.uow.committed


# ---------------------------------------------------------------------------
# ChapterService — sync only, no async jobs
# ---------------------------------------------------------------------------


class TestChapterServiceNoAsync:
    """Chapter operations never enqueue async jobs."""

    def setup_method(self) -> None:
        self.repo = StubChapterRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = ChapterService(uow_factory=self.factory, chapter_repo=self.repo)

    def test_create_does_not_enqueue_jobs(self) -> None:
        self.svc.create("c1", title="T", document_id="d1")
        assert self.uow.committed

    def test_update_does_not_enqueue_jobs(self) -> None:
        ch = Chapter(id="c1", title="Old", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.svc.update("c1", title="New")
        assert self.uow.committed

    def test_delete_does_not_enqueue_jobs(self) -> None:
        ch = Chapter(id="c1", title="T", state=DataState.SYNC)
        self.repo._store["c1"] = ch
        self.svc.delete("c1")
        assert self.uow.committed


# ---------------------------------------------------------------------------
# ParagraphService — async when content provided
# ---------------------------------------------------------------------------


class TestParagraphServiceAsync:
    """Paragraph create/update with content enqueue async jobs."""

    def setup_method(self) -> None:
        self.repo = StubParagraphRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.spy_queue = SpyJobQueue()
        self.mock_doc_cache = MagicMock()
        self.ctx = SessionContext(job_queue=self.spy_queue, doc_cache=self.mock_doc_cache)  # type: ignore[arg-type]
        self.svc = ParagraphService(
            uow_factory=self.factory,
            paragraph_repo=self.repo,
            session_context=self.ctx,
        )

    def test_create_enqueues_commit_job(self) -> None:
        s1 = Sentence(id="s1", state=DataState.NEW)
        self.svc.create("p1", content=[s1], chapter_id="ch1")
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 1

    def test_create_enqueues_delete_and_reconstruct_jobs(self) -> None:
        s1 = Sentence(id="s1", state=DataState.NEW)
        self.svc.create("p1", content=[s1], chapter_id="ch1")
        delete_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, DeleteJob)]
        reconstruct_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, ReconstructJob)]
        assert len(delete_jobs) >= 1
        assert len(reconstruct_jobs) >= 1

    def test_create_does_not_commit_uow_directly(self) -> None:
        s1 = Sentence(id="s1", state=DataState.NEW)
        self.svc.create("p1", content=[s1], chapter_id="ch1")
        assert not self.uow.committed

    def test_update_enqueues_jobs(self) -> None:
        s_old = Sentence(id="s_old", state=DataState.SYNC)
        p = Paragraph(id="p1", state=DataState.SYNC)
        p.append_child(s_old)
        self.repo._store["p1"] = p

        s_new = Sentence(id="s_new", state=DataState.NEW)
        self.svc.update("p1", content=[s_new], chapter_id="ch1")
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 1

    def test_delete_still_uses_sync_path(self) -> None:
        """Delete does not need tokenization — direct UoW commit."""
        p = Paragraph(id="p1", state=DataState.SYNC)
        self.repo._store["p1"] = p
        self.svc.delete("p1")
        assert self.uow.committed
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 0


# ---------------------------------------------------------------------------
# SentenceService — async when content provided
# ---------------------------------------------------------------------------


class TestSentenceServiceAsync:
    """Sentence create/update with content enqueue async jobs."""

    def setup_method(self) -> None:
        self.repo = StubSentenceRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.spy_queue = SpyJobQueue()
        self.mock_doc_cache = MagicMock()
        self.ctx = SessionContext(job_queue=self.spy_queue, doc_cache=self.mock_doc_cache)  # type: ignore[arg-type]
        self.svc = SentenceService(
            uow_factory=self.factory,
            sentence_repo=self.repo,
            session_context=self.ctx,
        )

    def test_create_enqueues_commit_job(self) -> None:
        self.svc.create("s1", text="Hello", paragraph_id="p1")
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 1

    def test_create_enqueues_delete_and_reconstruct_jobs(self) -> None:
        self.svc.create("s1", text="Hello", paragraph_id="p1")
        delete_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, DeleteJob)]
        reconstruct_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, ReconstructJob)]
        assert len(delete_jobs) >= 1
        assert len(reconstruct_jobs) >= 1

    def test_create_does_not_commit_uow_directly(self) -> None:
        self.svc.create("s1", text="Hello", paragraph_id="p1")
        assert not self.uow.committed

    def test_update_enqueues_jobs(self) -> None:
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s

        self.svc.update("s1", text="new", paragraph_id="p1")
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 1

    def test_delete_still_uses_sync_path(self) -> None:
        """Delete does not need tokenization — direct UoW commit."""
        s = Sentence(id="s1", state=DataState.SYNC)
        self.repo._store["s1"] = s
        self.svc.delete("s1")
        assert self.uow.committed
        commit_jobs = [j for j in self.spy_queue.enqueued if isinstance(j, CommitJob)]
        assert len(commit_jobs) == 0


# ---------------------------------------------------------------------------
# Service without SessionContext falls back to sync
# ---------------------------------------------------------------------------


class TestParagraphServiceSyncFallback:
    """When no SessionContext is provided, content changes use sync path."""

    def setup_method(self) -> None:
        self.repo = StubParagraphRepo()
        self.uow = StubUnitOfWork()
        self.factory = StubUnitOfWorkFactory(self.uow)
        self.svc = ParagraphService(
            uow_factory=self.factory,
            paragraph_repo=self.repo,
        )

    def test_create_without_context_commits_directly(self) -> None:
        s1 = Sentence(id="s1", state=DataState.NEW)
        self.svc.create("p1", content=[s1], chapter_id="ch1")
        assert self.uow.committed
