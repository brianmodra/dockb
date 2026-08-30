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
from typing import TYPE_CHECKING

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.semantics.async_reconstructor import AsyncReconstructor
from dockb.services.semantics.commit_job import CommitJob

if TYPE_CHECKING:
    from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
    from dockb.repositories.chapter_repository import ChapterRepository
    from dockb.repositories.document_repository import DocumentRepository
    from dockb.repositories.paragraph_repository import ParagraphRepository
    from dockb.repositories.sentence_repository import SentenceRepository
    from dockb.services.session_context import SessionContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document Service
# ---------------------------------------------------------------------------


class DocumentService:
    """CRUD operations for Document entities."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        document_repo: DocumentRepository,
    ) -> None:
        self._uow_factory = uow_factory
        self._document_repo = document_repo

    def list_all(self) -> list[dict[str, str]]:
        """Return lightweight summaries for every document."""
        return self._document_repo.list_all()

    def get(self, document_id: str) -> Document | None:
        """Load a full document hierarchy, or None."""
        return self._document_repo.load(document_id)

    def create(
        self,
        document_id: str,
        title: str,
        author: str,
    ) -> Document:
        """Create a new empty document and commit it."""
        doc = Document(id=document_id, title=title, author=author, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
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

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        chapter_repo: ChapterRepository,
    ) -> None:
        self._uow_factory = uow_factory
        self._chapter_repo = chapter_repo

    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        """Return chapter summaries for a document."""
        return self._chapter_repo.list_by_document(document_id)

    def get(self, chapter_id: str) -> Chapter | None:
        """Load a full chapter hierarchy, or None."""
        return self._chapter_repo.load(chapter_id)

    def create(
        self,
        chapter_id: str,
        title: str,
        document_id: str,
    ) -> Chapter:
        """Create a new empty chapter and commit it."""
        ch = Chapter(id=chapter_id, title=title, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id)
        uow.commit()
        return ch

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
