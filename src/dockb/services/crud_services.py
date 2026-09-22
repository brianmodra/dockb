"""Service layer connecting API requests to models and repositories.

Each service handles CRUD operations for one entity type.  Read operations
go directly through the repository; write operations modify in-memory
models, register them with the UnitOfWork, and commit.

Paragraph and Sentence services support an optional ``session_context``
that enables async processing (DeleteJob + ReconstructJob + CommitJob)
when content is provided.  Without a session context, content changes
commit synchronously.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dockb.exceptions import ChapterAfterNotFoundError, DuplicateTitleError
from dockb.infrastructure.document_store.store import DocumentMetadata
from dockb.infrastructure.markdown import front_matter
from dockb.infrastructure.markdown import writer as markdown_writer
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.markdown_import import ChapterImportSummary, apply_chapter_file
from dockb.services.semantics.async_reconstructor import AsyncReconstructor
from dockb.services.semantics.commit_job import CommitJob

if TYPE_CHECKING:
    from spacy.language import Language

    from dockb.infrastructure.document_store.store import DocumentStore
    from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
    from dockb.repositories.chapter_repository import ChapterRepository
    from dockb.repositories.document_repository import DocumentRepository
    from dockb.repositories.paragraph_repository import ParagraphRepository
    from dockb.repositories.sentence_repository import SentenceRepository
    from dockb.services.session_context import SessionContext

logger = logging.getLogger(__name__)


@dataclass
class ChapterSaveResult:
    """What saving a chapter's owned markdown file returned: canonical text plus a change summary."""

    content: str
    summary: ChapterImportSummary


# ---------------------------------------------------------------------------
# Document Service
# ---------------------------------------------------------------------------


class DocumentService:
    """CRUD operations for Document entities."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        document_repo: DocumentRepository,
        document_store: DocumentStore | None = None,
        nlp: Language | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._document_repo = document_repo
        self._document_store = document_store
        self._nlp = nlp

    def list_all(self) -> list[dict[str, str]]:
        """Return lightweight summaries for every document."""
        return self._document_repo.list_all()

    def get(self, document_id: str) -> Document | None:
        """Load a full document hierarchy, or None."""
        return self._document_repo.load(document_id)

    def open(self, document_id: str) -> Document | None:
        """Load a document, materializing its owned file tree when absent.

        When a store is configured and the document's directory does not exist
        yet, the tree (metadata + one chapter file per graph chapter) is
        serialized from the graph and committed to git, then the document is
        returned.
        """
        doc = self._document_repo.load(document_id)
        if doc is None:
            return None
        if self._document_store is not None and not self._document_store.document_exists(document_id):
            self._materialize(self._document_store, doc)
        return doc

    def _materialize(self, store: DocumentStore, doc: Document) -> None:
        """Write the document's owned tree from the graph and git-commit it."""
        store.write_metadata(doc.id, DocumentMetadata(title=doc.title, author=doc.author))
        for chapter in doc.chapters:
            content = markdown_writer.render_chapter_markdown(chapter, self._nlp)
            store.write_chapter(doc.id, chapter.id, content)
        store.git_commit(doc.id, f"materialize: {doc.id[:8]}")

    def create(
        self,
        document_id: str,
        title: str,
        author: str,
    ) -> Document:
        """Create a new empty document and commit it.

        An exact-title match against the knowledge graph is rejected, and the
        server-owned metadata file for the document is materialized when a
        document store is configured.
        """
        if any(row["title"] == title for row in self._document_repo.list_all()):
            raise DuplicateTitleError(title)

        doc = Document(id=document_id, title=title, author=author, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        if self._document_store is not None:
            self._document_store.write_metadata(document_id, DocumentMetadata(title=title, author=author))
        return doc

    def update(
        self,
        document_id: str,
        title: str,
        author: str,
    ) -> Document | None:
        """Update document attrs.  Returns None if not found."""
        doc = self._document_repo.load(document_id)
        if doc is None:
            return None
        doc.title = title
        doc.author = author
        doc.state = DataState.CHANGED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        return doc

    def delete(self, document_id: str) -> bool:
        """Delete a document and all children.  Returns False if not found."""
        doc = self._document_repo.load(document_id)
        if doc is None:
            return False
        doc.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        return True


# ---------------------------------------------------------------------------
# Chapter Service
# ---------------------------------------------------------------------------


class ChapterService:
    """CRUD operations for Chapter entities."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        uow_factory: UnitOfWorkFactory,
        chapter_repo: ChapterRepository,
        document_repo: DocumentRepository | None = None,
        document_store: DocumentStore | None = None,
        nlp: Language | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._chapter_repo = chapter_repo
        self._document_repo = document_repo
        self._document_store = document_store
        self._nlp = nlp
        self._save_locks: dict[str, threading.Lock] = {}
        self._save_users: dict[str, int] = {}
        self._save_registry_guard = threading.Lock()

    def _save_lock(self, chapter_id: str) -> threading.Lock:
        """Return the per-chapter save lock, registering *chapter_id* as in use.

        The caller must balance this with ``_save_release`` (use ``_save_scope``
        for a self-balancing context manager).
        """
        with self._save_registry_guard:
            lock = self._save_locks.get(chapter_id)
            if lock is None:
                lock = threading.Lock()
                self._save_locks[chapter_id] = lock
            self._save_users[chapter_id] = self._save_users.get(chapter_id, 0) + 1
            return lock

    def _save_release(self, chapter_id: str) -> None:
        """Release a ``_save_lock`` registration, evicting the entry when idle.

        The entry is dropped only once no holder and no waiter remain, so the
        registry does not grow per chapter id over a server's lifetime.
        """
        with self._save_registry_guard:
            users = self._save_users.get(chapter_id, 0) - 1
            if users <= 0:
                self._save_users.pop(chapter_id, None)
                self._save_locks.pop(chapter_id, None)
            else:
                self._save_users[chapter_id] = users

    @contextmanager
    def _save_scope(self, chapter_id: str) -> Iterator[None]:
        """Run one save/reconcile for *chapter_id* under its per-chapter lock.

        Saves to one chapter serialize (last-write-wins within the queue);
        distinct chapters proceed concurrently. Balances registration so the
        lock entry is evicted when idle.
        """
        lock = self._save_lock(chapter_id)
        try:
            with lock:
                yield
        finally:
            self._save_release(chapter_id)

    def list_by_document(self, document_id: str) -> list[dict[str, str | int]]:
        """Return chapter summaries (ordered by index) for a document."""
        return self._chapter_repo.list_by_document(document_id)

    def get(self, chapter_id: str) -> Chapter | None:
        """Load a full chapter hierarchy, or None."""
        return self._chapter_repo.load(chapter_id)

    def open(self, chapter_id: str) -> Chapter | None:
        """Load a chapter, materializing its owned markdown file when absent.

        When a store is configured, the chapter's owning document is resolved
        from the graph and, if ``chapter-{id}.md`` does not exist yet, the file
        is serialized from the graph and git-committed. Documents without a
        graph parent (orphans) are returned as-is.
        """
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        if self._document_store is None:
            return ch
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return ch
        if not self._document_store.chapter_exists(document_id, chapter_id):
            self._materialize_chapter(self._document_store, document_id, ch)
        return ch

    def save_document(self, chapter_id: str, content: str) -> ChapterSaveResult | None:
        """Save a chapter: write *content* to its owned file, rehydrate the graph, git-snap.

        The chapter's ``id``/``title`` are forced into the file's front matter
        (the server, not the editor, owns identity). The returned ``content`` is
        the canonical span-form text and ``summary`` records what changed.
        Returns ``None`` for a missing chapter, an orphan, or when no store /
        nlp is configured (the endpoint reports 404).
        """
        if self._document_store is None or self._nlp is None or self._document_repo is None:
            return None
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return None
        document = self._document_repo.load(document_id)
        if document is None:
            return None
        with self._save_scope(chapter_id):
            self._document_store.write_chapter(
                document_id,
                chapter_id,
                front_matter.merge(content, {"id": chapter_id, "title": ch.title}),
            )
            summary = apply_chapter_file(
                document,
                self._document_store.chapter_file(document_id, chapter_id),
                self._nlp,
                self._chapter_repo,
                self._uow_factory,
            )
            self._document_store.git_commit(document_id, f"save: chapter {chapter_id[:8]}")
        canonical = self._document_store.read_chapter(document_id, chapter_id)
        return ChapterSaveResult(content=canonical or "", summary=summary)

    def open_document(self, chapter_id: str) -> str | None:
        """Read a chapter's owned file as canonical text, reconciling it first.

        Materializes ``chapter-{id}.md`` from the graph when it is missing,
        otherwise absorbs any hand edit through ``apply_chapter_file()``, then
        git-snaps and returns the canonical text. Returns ``None`` for a missing
        chapter, an orphan, or when no store / nlp is configured (404).
        """
        if self._document_store is None or self._nlp is None or self._document_repo is None:
            return None
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return None
        document = self._document_repo.load(document_id)
        if document is None:
            return None
        with self._save_scope(chapter_id):
            if not self._document_store.chapter_exists(document_id, chapter_id):
                self._materialize_chapter(self._document_store, document_id, ch)
            else:
                apply_chapter_file(
                    document,
                    self._document_store.chapter_file(document_id, chapter_id),
                    self._nlp,
                    self._chapter_repo,
                    self._uow_factory,
                )
                self._document_store.git_commit(document_id, f"open: chapter {chapter_id[:8]}")
        return self._document_store.read_chapter(document_id, chapter_id)

    def _materialize_chapter(self, store: DocumentStore, document_id: str, ch: Chapter) -> None:
        """Write the chapter's owned markdown file from the graph and git-commit it."""
        content = markdown_writer.render_chapter_markdown(ch, self._nlp)
        store.write_chapter(document_id, ch.id, content)
        store.git_commit(document_id, f"materialize: chapter {ch.id[:8]}")

    def create(
        self,
        chapter_id: str,
        title: str,
        document_id: str,
        after_chapter_id: str | None = None,
    ) -> Chapter:
        """Create a new empty chapter, placed after *after_chapter_id*, and commit it.

        ``after_chapter_id=None`` places the chapter first (index 0). The empty
        ``chapter-{id}.md`` (front matter only) is written when a document store
        is configured.
        """
        index = self._resolve_index(document_id, after_chapter_id)
        ch = Chapter(id=chapter_id, title=title, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id, index=str(index))
        uow.commit()
        if self._document_store is not None:
            self._materialize_new_chapter(self._document_store, document_id, ch)
        return ch

    def _resolve_index(self, document_id: str, after_chapter_id: str | None) -> int:
        """Return the index of a new chapter placed after *after_chapter_id*."""
        if after_chapter_id is None:
            return 0
        for row in self._chapter_repo.list_by_document(document_id):
            if row["id"] == after_chapter_id:
                return int(row["index"]) + 1
        raise ChapterAfterNotFoundError(after_chapter_id)

    def _materialize_new_chapter(self, store: DocumentStore, document_id: str, ch: Chapter) -> None:
        """Write the new chapter's empty owned markdown file and git-commit it."""
        content = markdown_writer.render_chapter_markdown(ch, self._nlp)
        store.write_chapter(document_id, ch.id, content)
        store.git_commit(document_id, f"create: chapter {ch.id[:8]}")

    def update(
        self,
        chapter_id: str,
        title: str,
    ) -> Chapter | None:
        """Update chapter attrs.  Returns None if not found."""
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        ch.title = title
        ch.state = DataState.CHANGED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id="")
        uow.commit()
        return ch

    def delete(self, chapter_id: str) -> bool:
        """Delete a chapter and all children.  Returns False if not found."""
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return False
        ch.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id="")
        uow.commit()
        return True


# ---------------------------------------------------------------------------
# Paragraph Service
# ---------------------------------------------------------------------------


class ParagraphService:
    """CRUD operations for Paragraph entities."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        paragraph_repo: ParagraphRepository,
        session_context: SessionContext | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._paragraph_repo = paragraph_repo
        self._session_context = session_context

    def list_by_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        """Return paragraph summaries for a chapter."""
        return self._paragraph_repo.list_by_chapter(chapter_id)

    def get(self, paragraph_id: str) -> Paragraph | None:
        """Load a full paragraph hierarchy, or None."""
        return self._paragraph_repo.load(paragraph_id)

    def create(
        self,
        paragraph_id: str,
        content: list[Sentence],
        chapter_id: str,
    ) -> Paragraph:
        """Create a new paragraph with content and commit it."""
        para = Paragraph(id=paragraph_id, state=DataState.NEW)
        for sent in content:
            para.append_child(sent)

        if self._can_use_async():
            self._enqueue_content_jobs(para, chapter_id=chapter_id)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(para, chapter_id=chapter_id)
            uow.commit()
        return para

    def update(
        self,
        paragraph_id: str,
        content: list[Sentence],
        chapter_id: str | None = None,
    ) -> Paragraph | None:
        """Replace paragraph content.  Handles sentence gain/loss.

        Returns None if paragraph not found.
        """
        para = self._paragraph_repo.load(paragraph_id)
        if para is None:
            return None

        existing_ids = {s.id for s in para.sentences}
        new_ids = {s.id for s in content}

        for sid in existing_ids - new_ids:
            para.delete_child(sid)

        for sent in content:
            if sent.id not in existing_ids:
                para.append_child(sent)

        para.state = DataState.CHANGED

        if self._can_use_async():
            self._enqueue_content_jobs(para, chapter_id=chapter_id or "")
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(para, chapter_id=chapter_id or "")
            uow.commit()
        return para

    def delete(self, paragraph_id: str) -> bool:
        """Delete a paragraph and all children.  Returns False if not found."""
        para = self._paragraph_repo.load(paragraph_id)
        if para is None:
            return False
        para.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(para, chapter_id="")
        uow.commit()
        return True

    def _can_use_async(self) -> bool:
        """Return True if a session context with job queue is available."""
        return (
            self._session_context is not None
            and self._session_context.job_queue is not None
            and self._session_context.doc_cache is not None
        )

    def _enqueue_content_jobs(self, para: Paragraph, **parent_ids: str) -> None:
        """Enqueue DeleteJob + ReconstructJob + CommitJob for content changes."""
        assert self._session_context is not None
        jq = self._session_context.job_queue
        dc = self._session_context.doc_cache

        reconstructor = AsyncReconstructor(doc_cache=dc, queue=jq)  # type: ignore[arg-type]
        reconstructor.run(para)

        commit_job = CommitJob(self._uow_factory)
        commit_job.add(para, **parent_ids)
        jq.enqueue(commit_job)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Sentence Service
# ---------------------------------------------------------------------------


class SentenceService:
    """CRUD operations for Sentence entities."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        sentence_repo: SentenceRepository,
        session_context: SessionContext | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._sentence_repo = sentence_repo
        self._session_context = session_context

    def list_by_paragraph(self, paragraph_id: str) -> list[dict[str, str]]:
        """Return sentence summaries for a paragraph."""
        return self._sentence_repo.list_by_paragraph(paragraph_id)

    def get(self, sentence_id: str) -> Sentence | None:
        """Load a full sentence with tokens, or None."""
        return self._sentence_repo.load(sentence_id)

    def create(
        self,
        sentence_id: str,
        text: str,
        paragraph_id: str,
    ) -> Sentence:
        """Create a new sentence with text and commit it.

        The text is set on the sentence (marking it dirty).  Tokenisation
        happens asynchronously via the job queue when a session context is
        available, or synchronously via UoW commit otherwise.
        """
        sent = Sentence(id=sentence_id)
        sent.set_text(text)

        if self._can_use_async():
            self._enqueue_content_jobs(sent, paragraph_id=paragraph_id)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(sent, paragraph_id=paragraph_id)
            uow.flush_pending()
        return sent

    def update(
        self,
        sentence_id: str,
        text: str,
        paragraph_id: str | None = None,
    ) -> Sentence | None:
        """Replace sentence text.

        Returns None if sentence not found.
        """
        sent = self._sentence_repo.load(sentence_id)
        if sent is None:
            return None

        sent.set_text(text)

        if self._can_use_async():
            self._enqueue_content_jobs(sent, paragraph_id=paragraph_id or "")
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(sent, paragraph_id=paragraph_id or "")
            uow.flush_pending()
        return sent

    def delete(self, sentence_id: str) -> bool:
        """Delete a sentence and all tokens.  Returns False if not found."""
        sent = self._sentence_repo.load(sentence_id)
        if sent is None:
            return False
        sent.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(sent, paragraph_id="")
        uow.commit()
        return True

    def _can_use_async(self) -> bool:
        """Return True if a session context with job queue is available."""
        return (
            self._session_context is not None
            and self._session_context.job_queue is not None
            and self._session_context.doc_cache is not None
        )

    def _enqueue_content_jobs(self, sent: Sentence, **parent_ids: str) -> None:
        """Enqueue DeleteJob + ReconstructJob + CommitJob for content changes."""
        assert self._session_context is not None
        jq = self._session_context.job_queue
        dc = self._session_context.doc_cache

        reconstructor = AsyncReconstructor(doc_cache=dc, queue=jq)  # type: ignore[arg-type]
        reconstructor.run(sent)

        commit_job = CommitJob(self._uow_factory)
        commit_job.add(sent, **parent_ids)
        jq.enqueue(commit_job)  # type: ignore[union-attr]
