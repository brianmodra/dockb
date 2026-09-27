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
from typing import TYPE_CHECKING, Literal

from dockb.exceptions import ChapterAfterNotFoundError, ChapterCategoryMismatchError, DuplicateTitleError
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
from dockb.timing import measure

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
        serialized from the graph and committed to git; otherwise the metadata
        file is refreshed from the graph. The document is then returned.
        """
        doc = self._document_repo.load(document_id)
        if doc is None:
            return None
        if self._document_store is not None:
            if not self._document_store.document_exists(doc.title):
                self._materialize(self._document_store, doc)
            else:
                self._document_store.write_metadata(doc.title, DocumentMetadata(title=doc.title, author=doc.author))
        return doc

    def _materialize(self, store: DocumentStore, doc: Document) -> None:
        """Write the document's owned tree from the graph and git-commit it."""
        store.write_metadata(doc.title, DocumentMetadata(title=doc.title, author=doc.author))
        for chapter in doc.chapters:
            content = markdown_writer.render_chapter_markdown(chapter, self._nlp)
            store.write_chapter(doc.title, chapter.act, chapter.title, content, chapter.category)
        store.git_commit(doc.title, f"materialize: {doc.id[:8]}")

    def create(
        self,
        document_id: str,
        title: str,
        author: str,
    ) -> Document:
        """Create a new empty document and commit it.

        A case-insensitive title match against the knowledge graph is
        rejected, and the server-owned metadata file for the document is
        materialized when a document store is configured.
        """
        if any(str(row.get("title") or "").lower() == title.lower() for row in self._document_repo.list_all()):
            raise DuplicateTitleError(title)

        doc = Document(id=document_id, title=title, author=author, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        if self._document_store is not None:
            self._document_store.write_metadata(title, DocumentMetadata(title=title, author=author))
        return doc

    def update(
        self,
        document_id: str,
        title: str,
        author: str,
    ) -> Document | None:
        """Update document attrs, renaming the owned tree and refreshing the graph.

        Returns None if not found. The graph is updated first; a title change
        then git mv's the owned directory (metadata rewritten with the new
        title), and the metadata file is always brought in line with the graph.
        """
        doc = self._document_repo.load(document_id)
        if doc is None:
            return None
        for row in self._document_repo.list_all():
            if row["id"] != document_id and str(row.get("title") or "").lower() == title.lower():
                raise DuplicateTitleError(title)
        old_title = doc.title
        doc.title = title
        doc.author = author
        doc.state = DataState.CHANGED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        if self._document_store is not None:
            if title != old_title:
                self._document_store.rename_document(old_title, title)
            self._document_store.write_metadata(title, DocumentMetadata(title=title, author=author))
            self._document_store.git_commit(title, f"update: document {document_id[:8]}")
        return doc

    def delete(self, document_id: str) -> bool:
        """Delete a document: remove its owned store tree, then the graph subtree.

        The store directory (``git rm`` + commit) goes first so a failure leaves
        the graph intact for a retry. The graph DELETED write cascades to every
        chapter, paragraph, sentence, and token. Returns False if not found.
        """
        doc = self._document_repo.load(document_id)
        if doc is None:
            return False
        if self._document_store is not None:
            self._document_store.remove_document(doc.title)
        doc.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        return True


# ---------------------------------------------------------------------------
# Chapter Service
# ---------------------------------------------------------------------------


def _row_category(row: dict[str, str | int]) -> str:
    """Return a list-row's category, defaulting old rows to ``Chapter``."""
    return str(row.get("category") or "Chapter")


def _crosses_category(members: list[dict[str, str | int]], mover: Chapter, after_chapter_id: str | None) -> bool:
    """Return whether *mover* would land outside its own category.

    Landing after a same-category chapter stays inside the block. Landing
    after a different category is allowed only at the front of the mover's
    own block — the following sibling (ignoring the mover) is the same
    category. Moving first crosses when the chapter it would precede is a
    different category.
    """
    mover_category = mover.category or "Chapter"
    without_mover = [row for row in members if str(row["id"]) != mover.id]
    if after_chapter_id is None:
        return bool(without_mover) and _row_category(without_mover[0]) != mover_category
    after_index = next((index for index, row in enumerate(without_mover) if str(row["id"]) == after_chapter_id), None)
    if after_index is None or _row_category(without_mover[after_index]) == mover_category:
        return False
    following = without_mover[after_index + 1] if after_index + 1 < len(without_mover) else None
    return following is None or _row_category(following) != mover_category


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
        if self._document_store is None or self._document_repo is None:
            return ch
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return ch
        document = self._document_repo.load(document_id)
        if document is None:
            return ch
        if not self._document_store.chapter_exists(document.title, ch.act, ch.title, ch.category):
            self._materialize_chapter(self._document_store, document, ch)
        return ch

    def save_document(self, chapter_id: str, content: str) -> ChapterSaveResult | None:
        """Save a chapter: write *content* to its owned file, rehydrate the graph, git-snap.

        The chapter's ``id``/``title`` (and its ``act``/``category`` when set)
        are forced
        into the file's front matter — the server, not the editor, owns
        identity. The returned ``content`` is the canonical span-form text and
        ``summary`` records what changed. Returns ``None`` for a missing
        chapter, an orphan, or when no store / nlp is configured (the endpoint
        reports 404).
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
            updates = {"id": chapter_id, "title": ch.title}
            if ch.act:
                updates["act"] = ch.act
            updates["category"] = ch.category
            self._document_store.write_chapter(
                document.title,
                ch.act,
                ch.title,
                front_matter.merge(content, updates),
                ch.category,
            )
            summary = apply_chapter_file(
                document,
                self._document_store.chapter_file(document.title, ch.act, ch.title, ch.category),
                self._nlp,
                self._chapter_repo,
                self._uow_factory,
            )
            self._document_store.git_commit(document.title, f"save: chapter {chapter_id[:8]}")
        canonical = self._document_store.read_chapter(document.title, ch.act, ch.title, ch.category)
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
        with measure("repo.chapter.load"):
            ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        with measure("repo.chapter.find_document_id"):
            document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return None
        with measure("repo.document.load"):
            document = self._document_repo.load(document_id)
        if document is None:
            return None
        with self._save_scope(chapter_id):
            if not self._document_store.chapter_exists(document.title, ch.act, ch.title, ch.category):
                with measure("stage.materialize"):
                    self._materialize_chapter(self._document_store, document, ch)
            else:
                with measure("stage.apply_chapter_file"):
                    apply_chapter_file(
                        document,
                        self._document_store.chapter_file(document.title, ch.act, ch.title, ch.category),
                        self._nlp,
                        self._chapter_repo,
                        self._uow_factory,
                    )
                with measure("stage.git_commit"):
                    self._document_store.git_commit(document.title, f"open: chapter {chapter_id[:8]}")
        with measure("stage.read_chapter"):
            return self._document_store.read_chapter(document.title, ch.act, ch.title, ch.category)

    def _materialize_chapter(self, store: DocumentStore, document: Document, ch: Chapter) -> None:
        """Write the chapter's owned markdown file from the graph and git-commit it."""
        content = markdown_writer.render_chapter_markdown(ch, self._nlp)
        store.write_chapter(document.title, ch.act, ch.title, content, ch.category)
        store.git_commit(document.title, f"materialize: chapter {ch.id[:8]}")

    def create(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        chapter_id: str,
        title: str,
        document_id: str,
        after_chapter_id: str | None = None,
        category: Literal["Chapter", "Character"] = "Chapter",
    ) -> Chapter:
        """Create a new empty chapter, placed after *after_chapter_id*, and commit it.

        ``after_chapter_id=None`` places the chapter first (index 0). The empty
        ``chapter-{id}.md`` (front matter only) is written when a document store
        is configured.
        """
        index = self._resolve_index(document_id, after_chapter_id)
        for row in self._chapter_repo.list_by_document(document_id):
            if str(row.get("title") or "").lower() == title.lower():
                raise DuplicateTitleError(title)
        ch = Chapter(id=chapter_id, title=title, category=category, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id, index=str(index))
        uow.commit()
        if self._document_store is not None and self._document_repo is not None:
            document = self._document_repo.load(document_id)
            if document is not None:
                self._materialize_new_chapter(self._document_store, document, ch)
        return ch

    def _resolve_index(self, document_id: str, after_chapter_id: str | None) -> int:
        """Return the index of a new chapter placed after *after_chapter_id*."""
        if after_chapter_id is None:
            return 0
        for row in self._chapter_repo.list_by_document(document_id):
            if row["id"] == after_chapter_id:
                return int(row["index"]) + 1
        raise ChapterAfterNotFoundError(after_chapter_id)

    def _materialize_new_chapter(self, store: DocumentStore, document: Document, ch: Chapter) -> None:
        """Write the new chapter's empty owned markdown file and git-commit it."""
        content = markdown_writer.render_chapter_markdown(ch, self._nlp)
        store.write_chapter(document.title, ch.act, ch.title, content, ch.category)
        store.git_commit(document.title, f"create: chapter {ch.id[:8]}")

    def move(self, chapter_id: str, after_chapter_id: str | None) -> Chapter | None:
        """Move *chapter_id* to follow *after_chapter_id*, or first when None.

        Returns None when the chapter does not exist or is orphaned, raises
        ``ChapterAfterNotFoundError`` when *after_chapter_id* is not a chapter
        of the same document.  Moving a chapter after itself is a no-op.

        The moved chapter adopts its neighbour's ``act`` (the server owns it):
        the act of the chapter it is placed after, or — when moved first — the
        act of the chapter it is placed before (the document's old first
        chapter). The adoption is skipped when the move leaves the order
        unchanged, and when the neighbour is a different category (a move to
        the front of the mover's own block). A move that would land outside
        the mover's category — including moving first ahead of the other
        category — raises ``ChapterCategoryMismatchError`` and changes nothing.
        """
        ch = self._chapter_repo.load(chapter_id)
        if ch is None or chapter_id == after_chapter_id:
            return ch
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is None:
            return None
        members = self._chapter_repo.list_by_document(document_id)
        if after_chapter_id is not None and after_chapter_id not in {row["id"] for row in members}:
            raise ChapterAfterNotFoundError(after_chapter_id)
        if _crosses_category(members, ch, after_chapter_id):
            raise ChapterCategoryMismatchError(chapter_id)
        ordered_ids = [str(row["id"]) for row in members]
        old_order = list(ordered_ids)
        ordered_ids.remove(chapter_id)
        if after_chapter_id is None:
            ordered_ids.insert(0, chapter_id)
        else:
            ordered_ids.insert(ordered_ids.index(after_chapter_id) + 1, chapter_id)
        if ordered_ids != old_order:
            neighbor = members[0] if after_chapter_id is None else next(row for row in members if row["id"] == after_chapter_id)
            if _row_category(neighbor) == (ch.category or "Chapter"):
                adopted_act = str(neighbor.get("act") or "")
                if ch.act != adopted_act:
                    ch.act = adopted_act
                    ch.state = DataState.CHANGED
                    uow = self._uow_factory.get_unit_of_work()
                    uow.register(ch, document_id=document_id)
                    uow.commit()
        self._chapter_repo.reorder(document_id, ordered_ids)
        return ch

    def update(
        self,
        chapter_id: str,
        title: str,
    ) -> Chapter | None:
        """Update the chapter title, renaming its owned file and refreshing the graph.

        Returns None if not found. The graph is updated first; a title change
        then git mv's the markdown file and rewrites the front matter title to
        match.
        """
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return None
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if document_id is not None:
            for row in self._chapter_repo.list_by_document(document_id):
                if row["id"] != chapter_id and str(row.get("title") or "").lower() == title.lower():
                    raise DuplicateTitleError(title)
        old_title = ch.title
        ch.title = title
        ch.state = DataState.CHANGED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id or "")
        uow.commit()
        if self._document_store is not None and self._document_repo is not None and document_id is not None and title != old_title:
            document = self._document_repo.load(document_id)
            if document is not None:
                self._document_store.rename_chapter(document.title, ch.act, old_title, title, ch.category)
        return ch

    def delete(self, chapter_id: str) -> bool:
        """Delete a chapter: remove its owned store file, then the graph subtree.

        The markdown file (``git rm`` + commit) goes first so a failure leaves
        the graph intact for a retry. The graph DELETED write cascades to the
        chapter's paragraphs, sentences, and tokens. Returns False if not found.
        """
        ch = self._chapter_repo.load(chapter_id)
        if ch is None:
            return False
        document_id = self._chapter_repo.find_document_id(chapter_id)
        if self._document_store is not None and self._document_repo is not None and document_id is not None:
            document = self._document_repo.load(document_id)
            if document is not None:
                self._document_store.remove_chapter(document.title, ch.act, ch.title, ch.category)
        ch.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id or "")
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
