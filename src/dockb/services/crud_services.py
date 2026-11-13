"""Service layer connecting API requests to models and repositories.

Each service handles CRUD operations for one entity type.  Read operations
go directly through the repository; write operations modify in-memory
models, register them with the UnitOfWork, and commit.

Paragraph and Sentence services support an optional ``session_context``
that enables async processing (DeleteJob + ReconstructJob + CommitJob)
when content is provided.  Without a session context, content changes
commit synchronously.
"""

# pylint: disable=too-many-lines

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

from dockb.exceptions import (
    ChapterAfterNotFoundError,
    ChapterCategoryMismatchError,
    ChapterNotFoundError,
    DocumentNotFoundError,
    DocumentOwnershipError,
    DuplicateTitleError,
    ParagraphNotFoundError,
)
from dockb.infrastructure.document_store.journal import JournalRecord
from dockb.infrastructure.document_store.store import ChapterRename, DocumentMetadata
from dockb.infrastructure.markdown import front_matter
from dockb.infrastructure.markdown import writer as markdown_writer
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.narrative_perspectives import validate_narrative_perspective
from dockb.services.chapter_front_matter import set_pov as apply_set_pov
from dockb.services.chapter_renumber import plan_renumber
from dockb.services.document_locks import DocumentLocks
from dockb.services.markdown_import import ChapterImportSummary, apply_chapter_file
from dockb.services.mentions import DocumentMentionsJob, MentionsJob
from dockb.services.mentions_scheduler import MentionsScheduler
from dockb.services.semantics.async_reconstructor import AsyncReconstructor
from dockb.services.semantics.commit_job import CommitJob
from dockb.timing import measure

if TYPE_CHECKING:
    from spacy.language import Language

    from dockb.infrastructure.document_store.factory import DocumentStoreFactory
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
    """CRUD operations for Document entities, always scoped to one owning account.

    Every method takes the account id it is acting for. There is no unscoped
    entry point, so a caller cannot reach another account's document by forgetting to
    pass one: an id that *owner* does not own reads as absent.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        uow_factory: UnitOfWorkFactory,
        document_repo: DocumentRepository,
        document_store_factory: DocumentStoreFactory | None = None,
        nlp: Language | None = None,
        document_locks: DocumentLocks | None = None,
        chapter_service: ChapterService | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._document_repo = document_repo
        self._document_store_factory = document_store_factory
        self._nlp = nlp
        self._document_locks = document_locks or DocumentLocks()
        self._chapter_service = chapter_service

    def _store(self, owner: str) -> DocumentStore | None:
        """Return *owner*'s document store, or None when no store is configured."""
        if self._document_store_factory is None:
            return None
        return self._document_store_factory.for_account(owner)

    @staticmethod
    def _metadata_for(store: DocumentStore, title: str, author: str, narrative_perspective: str) -> DocumentMetadata:
        """Build a metadata record for *title*, preserving fields this build does not know.

        Replacing the existing record rather than constructing a fresh one keeps any
        extra keys a newer metadata format wrote, which this service must not drop
        when it only means to change the title or author.
        """
        existing = store.read_metadata(title)
        if existing is None:
            return DocumentMetadata(title=title, author=author)
        updates: dict[str, str] = {"title": title, "author": author}
        if hasattr(existing, "narrative_perspective"):
            updates["narrative_perspective"] = narrative_perspective
        return replace(existing, **updates)

    def list_all(self, *, owner: str) -> list[dict[str, str]]:
        """Return lightweight summaries for every document *owner* owns."""
        return self._document_repo.list_all(owner)

    def get(self, document_id: str, *, owner: str) -> Document | None:
        """Load a full document hierarchy, or None when *owner* does not own it."""
        return self._document_repo.load(document_id, owner)

    def get_attrs(self, document_id: str, *, owner: str) -> dict[str, str] | None:
        """Return a document's attrs only, without loading the hierarchy or touching the store.

        Mirrors the expensive ``get``/``open`` paths but reads just the document
        node; it materializes nothing and writes no file tree, which keeps the
        settings dialog cheap.
        """
        return self._document_repo.load_attrs(document_id, owner)

    def open(self, document_id: str, *, owner: str) -> Document | None:
        """Load a document, materializing its owned file tree when absent.

        When a store is configured and the document's directory does not exist
        yet, the tree (metadata + one chapter file per graph chapter) is
        serialized from the graph and committed to git; otherwise the metadata
        file is refreshed from the graph. The document is then returned.

        Returns None when *owner* does not own the document, and writes nothing —
        the tree belongs to whoever does own it.
        """
        doc = self._document_repo.load(document_id, owner)
        if doc is None:
            return None
        store = self._store(owner)
        if store is not None:
            metadata = DocumentMetadata(
                title=doc.title,
                author=doc.author,
                narrative_perspective=doc.narrative_perspective,
            )
            if not store.document_exists(doc.title):
                self._materialize(store, doc)
            else:
                store.write_metadata(doc.title, metadata)
        return doc

    def _materialize(self, store: DocumentStore, doc: Document) -> None:
        """Write the document's owned tree from the graph and git-commit it.

        A chapter's `pov` is stored in the graph as the character chapter's **id**;
        the front matter carries the character's **title** instead, resolved here
        from the document's own character chapters — a pov id that resolves to
        nothing (the character chapter was deleted) writes no pov line at all.
        """
        titles = {chapter.id: chapter.title for chapter in doc.chapters if chapter.category == "Character"}
        store.write_metadata(
            doc.title,
            DocumentMetadata(
                title=doc.title,
                author=doc.author,
                narrative_perspective=doc.narrative_perspective,
            ),
        )
        for chapter in doc.chapters:
            attrs: dict[str, object] = {"id": chapter.id, "title": chapter.title}
            if chapter.act:
                attrs["act"] = chapter.act
            attrs["category"] = chapter.category
            pov_title = titles.get(chapter.pov, "")
            if pov_title:
                attrs["pov"] = pov_title
            content = markdown_writer.render_chapter_markdown(chapter, self._nlp, attrs=attrs)
            store.write_chapter(doc.title, chapter.act, chapter.title, content, chapter.category)
        store.git_commit(doc.title, f"materialize: {doc.id[:8]}")

    def create(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        document_id: str,
        title: str,
        author: str,
        owner: str,
        narrative_perspective: str = "",
    ) -> Document:
        """Create a new empty document owned by *owner* and commit it.

        A case-insensitive title match against *owner*'s documents is rejected, so two
        accounts may each hold a document with the same title. The server-owned metadata
        file for the document is materialized when a document store is configured.

        Raises DocumentOwnershipError when *owner* is blank, before anything is
        written: a document with no account has no directory to keep its manuscript
        in, and a node committed first would belong to nobody.
        """
        if not owner or not owner.strip():
            raise DocumentOwnershipError("an account id is required to create a document")
        narrative_perspective = validate_narrative_perspective(narrative_perspective)
        if any(str(row.get("title") or "").lower() == title.lower() for row in self._document_repo.list_all(owner)):
            raise DuplicateTitleError(title)

        doc = Document(
            id=document_id,
            title=title,
            author=author,
            owner=owner,
            narrative_perspective=narrative_perspective,
            state=DataState.NEW,
        )
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        uow.commit()
        store = self._store(owner)
        if store is not None:
            store.write_metadata(
                title,
                DocumentMetadata(title=title, author=author, narrative_perspective=narrative_perspective),
            )
        return doc

    def update(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        document_id: str,
        title: str,
        author: str,
        owner: str,
        narrative_perspective: str = "",
    ) -> Document | None:
        """Update document attrs, renaming the owned tree and refreshing the graph.

        Returns None when *owner* does not own the document, which is deliberately the
        same answer as when no such document exists. A title change with a document
        store is journaled before anything moves: the record names the old and new
        titles, so a crash between the git mv and the graph commit is repaired at the
        next boot by ``recover``. Without a store, or when the title is unchanged,
        there is no cross-store state to repair and the graph commits directly. The
        whole update runs under the document's exclusive lock, so a structural rename
        never interleaves with a save of one of its chapters.
        """
        with self._document_locks.exclusive(document_id):
            return self._update(document_id, title, author, owner, narrative_perspective)

    def _update(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        document_id: str,
        title: str,
        author: str,
        owner: str,
        narrative_perspective: str = "",
    ) -> Document | None:
        doc = self._document_repo.load(document_id, owner)
        if doc is None:
            return None
        narrative_perspective = validate_narrative_perspective(narrative_perspective)
        for row in self._document_repo.list_all(owner):
            if row["id"] != document_id and str(row.get("title") or "").lower() == title.lower():
                raise DuplicateTitleError(title)
        old_title = doc.title
        doc.title = title
        doc.author = author
        doc.narrative_perspective = narrative_perspective
        doc.state = DataState.CHANGED
        store = self._store(owner)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(doc)
        if store is None or title == old_title:
            uow.commit()
            if store is not None:
                store.write_metadata(
                    title,
                    self._metadata_for(store, title, author, narrative_perspective),
                )
                store.git_commit(title, f"update: document {document_id[:8]}")
            return doc
        journal = store.journal()
        record = JournalRecord.new(
            "document-rename",
            account_id=owner,
            document_id=document_id,
            payload={"from": old_title, "to": title},
        )
        journal.write(record)
        store.rename_document(old_title, title)
        uow.commit()
        store.write_metadata(
            title,
            self._metadata_for(store, title, author, narrative_perspective),
        )
        store.git_commit(title, f"update: document {document_id[:8]}")
        journal.remove(record.op_id)
        return doc

    def recover(self) -> list[str]:
        """Drain every account's intent journal, driving each record to its end state.

        Idempotent: a record whose operation already completed is a no-op, so this is
        safe to run on every boot. Returns human-readable warnings for records that
        could not be applied; those are quarantined rather than silently dropped, and
        never stop the remaining records from being replayed.
        """
        factory = self._document_store_factory
        if factory is None:
            return []
        warnings: list[str] = []
        for account_id in factory.journal_accounts():
            journal = factory.journal_for(account_id)
            for record in journal.pending():
                try:
                    self._recover_record(record)
                except Exception as exc:  # pylint: disable=broad-except
                    journal.quarantine(record.op_id)
                    warning = f"journal record {record.op_id} ({record.op}) for {account_id}: {exc}"
                    logger.warning(warning)
                    warnings.append(warning)
                else:
                    journal.remove(record.op_id)
        return warnings

    def _recover_record(self, record: JournalRecord) -> None:
        """Apply one journal record's desired end state."""
        if record.op == "document-rename":
            self._recover_document_rename(record)
            return
        if record.op in ("chapter-rename", "chapter-renumber"):
            if self._chapter_service is None:
                raise ValueError(f"{record.op!r} record needs a chapter service")
            self._chapter_service.recover_record(record)
            return
        raise ValueError(f"unknown journal operation {record.op!r}")

    def _recover_document_rename(self, record: JournalRecord) -> None:
        """Drive a document rename to ``payload['to']`` across the store and the graph.

        The git mv is idempotent only when the source is already gone; two existing
        directories are ambiguous and raise, which quarantines the record. Metadata is
        always refreshed from the graph so an author change that landed in the graph
        but not on disk is healed too.
        """
        from_title = record.payload.get("from")
        to_title = record.payload.get("to")
        if not from_title or not to_title:
            raise ValueError("document-rename record needs both 'from' and 'to'")
        factory = self._document_store_factory
        if factory is None:
            raise RuntimeError("a document store is required to replay a rename")
        store = factory.for_account(record.account_id)
        store.rename_document(from_title, to_title)
        shell = self._document_repo.load_shell(record.document_id, record.account_id)
        if shell is None:
            return
        if shell.title != to_title:
            doc = Document(
                id=record.document_id,
                title=to_title,
                author=shell.author,
                owner=record.account_id,
                narrative_perspective=shell.narrative_perspective,
                state=DataState.CHANGED,
            )
            uow = self._uow_factory.get_unit_of_work()
            uow.register(doc)
            uow.commit()
        store.write_metadata(
            to_title,
            self._metadata_for(store, to_title, shell.author, shell.narrative_perspective),
        )
        store.git_commit(to_title, f"recover: document {record.document_id[:8]}")

    def delete(self, document_id: str, *, owner: str) -> bool:
        """Delete a document: remove its owned store tree, then the graph subtree.

        The store directory (``git rm`` + commit) goes first so a failure leaves
        the graph intact for a retry. The graph DELETED write cascades to every
        chapter, paragraph, sentence, and token. Returns False when *owner* does not
        own the document, leaving both the tree and the graph untouched. The whole
        delete holds the document's exclusive lock.
        """
        doc = self._document_repo.load(document_id, owner)
        if doc is None:
            return False
        with self._document_locks.exclusive(document_id):
            store = self._store(owner)
            if store is not None:
                store.remove_document(doc.title)
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


class ChapterService:  # pylint: disable=too-many-instance-attributes
    """CRUD operations for Chapter entities."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        uow_factory: UnitOfWorkFactory,
        chapter_repo: ChapterRepository,
        document_repo: DocumentRepository | None = None,
        document_store_factory: DocumentStoreFactory | None = None,
        nlp: Language | None = None,
        mentions_repo: Any | None = None,
        session_context: SessionContext | None = None,
        mentions_scheduler: MentionsScheduler | None = None,
        mentions_chapter_repo: ChapterRepository | None = None,
        document_locks: DocumentLocks | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._chapter_repo = chapter_repo
        self._document_repo = document_repo
        self._document_store_factory = document_store_factory
        self._nlp = nlp
        self._mentions_repo = mentions_repo
        # The background mention evaluation reads through its own repositories
        # (wired on a separate session in production) so it never contends with
        # the request path; tests that omit them fall back to the request repos.
        self._mentions_chapter_repo = mentions_chapter_repo if mentions_chapter_repo is not None else chapter_repo
        self._mentions_scheduler = mentions_scheduler or MentionsScheduler()
        self._session_context = session_context
        self._document_locks = document_locks or DocumentLocks()
        self._save_locks: dict[str, threading.Lock] = {}
        self._save_users: dict[str, int] = {}
        self._save_registry_guard = threading.Lock()

    def recover_record(self, record: JournalRecord) -> None:
        """Apply one chapter-scoped journal record's desired end state."""
        if record.op == "chapter-rename":
            self._recover_chapter_rename(record)
            return
        if record.op == "chapter-renumber":
            self._recover_chapter_renumber(record)
            return
        raise ValueError(f"unknown journal operation {record.op!r}")

    def _recover_chapter_rename(self, record: JournalRecord) -> None:
        """Drive a chapter rename to ``payload['to']`` across the store and the graph."""
        payload = record.payload
        chapter_id = payload.get("chapter_id")
        document_title = payload.get("document_title")
        from_title = payload.get("from")
        to_title = payload.get("to")
        if not (chapter_id and document_title and from_title and to_title):
            raise ValueError("chapter-rename record is incomplete")
        factory = self._document_store_factory
        if factory is None:
            raise RuntimeError("a document store is required to replay a chapter rename")
        store = factory.for_account(record.account_id)
        act = str(payload.get("act") or "")
        category = str(payload.get("category") or "Chapter")
        store.rename_chapter(document_title, act, from_title, to_title, category)
        ch = self._chapter_repo.load(chapter_id, record.account_id)
        if ch is not None and ch.title != to_title:
            ch.title = to_title
            ch.state = DataState.CHANGED
            uow = self._uow_factory.get_unit_of_work()
            uow.register(ch, document_id=record.document_id or "", owner=record.account_id)
            uow.commit()

    def _recover_chapter_renumber(self, record: JournalRecord) -> None:
        """Drive a chapter renumber to its planned titles across the store and the graph."""
        payload = record.payload
        document_title = payload.get("document_title")
        if not document_title:
            raise ValueError("chapter-renumber record is incomplete")
        factory = self._document_store_factory
        if factory is None:
            raise RuntimeError("a document store is required to replay a renumber")
        store = factory.for_account(record.account_id)
        moves = [
            ChapterRename(
                act=str(move.get("act") or ""),
                category=str(move.get("category") or "Chapter"),
                old_title=str(move["old_title"]),
                new_title=str(move["new_title"]),
            )
            for move in payload.get("moves") or []
        ]
        entries = [{"id": str(entry["id"]), "title": str(entry["title"])} for entry in payload.get("entries") or []]
        store.renumber_chapters(document_title, moves)
        self._chapter_repo.retitle(record.document_id, entries, record.account_id)

    def _store(self, owner: str) -> DocumentStore | None:
        """Return *owner*'s document store, or None when no store is configured."""
        if self._document_store_factory is None:
            return None
        return self._document_store_factory.for_account(owner)

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

    def list_by_document(self, document_id: str, *, owner: str) -> list[dict[str, str | int]]:
        """Return chapter summaries (ordered by index) for *owner*'s document.

        A document the caller does not own lists the same as one with no chapters:
        an empty list. Both mean the same thing to the caller — nothing here.
        """
        return self._chapter_repo.list_by_document(document_id, owner)

    def get(self, chapter_id: str, *, owner: str) -> Chapter | None:
        """Load a full chapter hierarchy, or None.

        None also covers a chapter of another account's document, so a chapter id
        belonging to someone else is no more confirmable than one never created.
        """
        return self._chapter_repo.load(chapter_id, owner)

    def open(self, chapter_id: str, *, owner: str) -> Chapter | None:
        """Load a chapter, materializing its owned markdown file when absent.

        When a store is configured, the chapter's owning document is resolved
        from the graph and, if ``chapter-{id}.md`` does not exist yet, the file
        is serialized from the graph and git-committed. Documents without a
        graph parent (orphans) are returned as-is.

        *owner* selects which account's store the file is written under, and the
        owning document is loaded scoped to that account, so a chapter belonging to
        someone else resolves to no document and nothing is written.
        """
        ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        store = self._store(owner)
        if store is None or self._document_repo is None:
            return ch
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return ch
        document = self._document_repo.load_shell(document_id, owner)
        if document is None:
            return ch
        if not store.chapter_exists(document.title, ch.act, ch.title, ch.category):
            self._materialize_chapter(store, document, ch)
        return ch

    def save_document(self, chapter_id: str, content: str, *, owner: str) -> ChapterSaveResult | None:
        """Save a chapter: write *content* to its owned file, rehydrate the graph, git-snap.

        The chapter's ``id``/``title`` (and its ``act``/``category`` when set) are forced
        into the file's front matter — the server, not the editor, owns identity. The
        returned ``content`` is the canonical span-form text and ``summary`` records what
        changed. Returns ``None`` for a missing chapter, a chapter *owner* does not own,
        an orphan, or when no store / nlp is configured (the endpoint reports 404).
        """
        store = self._store(owner)
        if store is None or self._nlp is None or self._document_repo is None:
            return None
        with measure("repo.chapter.load"):
            ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        before_identity = (ch.first_name, ch.surname, tuple(ch.middle_names), tuple(ch.nicknames))
        with measure("repo.chapter.find_document_id"):
            document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return None
        with measure("repo.document.load"):
            document = self._document_repo.load_shell(document_id, owner)
        if document is None:
            return None
        with self._document_locks.shared(document_id), self._save_scope(chapter_id):
            updates = {"id": chapter_id, "title": ch.title}
            if ch.act:
                updates["act"] = ch.act
            updates["category"] = ch.category
            with measure("stage.write_chapter"):
                store.write_chapter(
                    document.title,
                    ch.act,
                    ch.title,
                    front_matter.merge(content, updates),
                    ch.category,
                )
            with measure("stage.apply_chapter_file"):
                summary = apply_chapter_file(
                    document,
                    store.chapter_file(document.title, ch.act, ch.title, ch.category),
                    self._nlp,
                    self._chapter_repo,
                    self._uow_factory,
                    owner=owner,
                    preloaded=ch,
                )
            with measure("stage.git_commit"):
                store.git_commit(document.title, f"save: chapter {chapter_id[:8]}")
        with measure("stage.trigger_mentions"):
            self._trigger_mentions(ch, document_id, before_identity, owner)
        with measure("stage.read_chapter"):
            canonical = store.read_chapter(document.title, ch.act, ch.title, ch.category)
        return ChapterSaveResult(content=canonical or "", summary=summary)

    def _trigger_mentions(
        self,
        ch: Chapter,
        document_id: str,
        before_identity: tuple[str, str, tuple[str, ...], tuple[str, ...]],
        owner: str,
    ) -> None:
        """Schedule the mention evaluation the save made necessary.

        A manuscript save schedules its own chapter; a character save whose
        identity changed schedules one job for the whole document (the
        ambiguity of a shared name is decided by every character's name set);
        anything else schedules nothing. The scheduler coalesces jobs by the
        chapter that triggered them, so re-saving the same chapter cancels its
        superseded evaluation and queues the fresh state.
        """
        if self._mentions_repo is None:
            return
        after_identity = (ch.first_name, ch.surname, tuple(ch.middle_names), tuple(ch.nicknames))
        identity_changed = ch.category == "Character" and after_identity != before_identity
        if ch.category == "Character" and not identity_changed:
            return
        if identity_changed:
            self._mentions_scheduler.schedule(
                ch.id,
                partial(
                    DocumentMentionsJob,
                    document_id=document_id,
                    mentions_repo=self._mentions_repo,
                    chapter_repo=self._mentions_chapter_repo,
                    owner=owner,
                ),
            )
        else:
            self._mentions_scheduler.schedule(
                ch.id,
                partial(
                    MentionsJob,
                    chapter_id=ch.id,
                    mentions_repo=self._mentions_repo,
                    chapter_repo=self._mentions_chapter_repo,
                    owner=owner,
                ),
            )

    def open_document(self, chapter_id: str, *, owner: str, readonly: bool = False) -> str | None:
        """Read a chapter's owned file as canonical text, reconciling it first.

        Materializes ``chapter-{id}.md`` from the graph when it is missing,
        otherwise absorbs any hand edit through ``apply_chapter_file()``, then
        git-snaps and returns the canonical text. With ``readonly`` an existing
        file is returned as-is — no reconciliation, no git write — and only a
        missing file is materialised. Returns ``None`` for a missing chapter, a
        chapter *owner* does not own, an orphan, or when no store / nlp is
        configured (404).
        """
        store = self._store(owner)
        if store is None or self._nlp is None or self._document_repo is None:
            return None
        with measure("repo.chapter.load"):
            ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        with measure("repo.chapter.find_document_id"):
            document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return None
        with measure("repo.document.load"):
            document = self._document_repo.load_shell(document_id, owner)
        if document is None:
            return None
        with self._document_locks.shared(document_id), self._save_scope(chapter_id):
            if not store.chapter_exists(document.title, ch.act, ch.title, ch.category):
                with measure("stage.materialize"):
                    self._materialize_chapter(store, document, ch)
            elif not readonly:
                with measure("stage.apply_chapter_file"):
                    apply_chapter_file(
                        document,
                        store.chapter_file(document.title, ch.act, ch.title, ch.category),
                        self._nlp,
                        self._chapter_repo,
                        self._uow_factory,
                        owner=owner,
                        preloaded=ch,
                    )
                with measure("stage.git_commit"):
                    store.git_commit(document.title, f"open: chapter {chapter_id[:8]}")
        with measure("stage.read_chapter"):
            return store.read_chapter(document.title, ch.act, ch.title, ch.category)

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
        *,
        owner: str,
    ) -> Chapter:
        """Create a new empty chapter, placed after *after_chapter_id*, and commit it.

        ``after_chapter_id=None`` places the chapter first (index 0). The empty
        ``chapter-{id}.md`` (front matter only) is written when a document store
        is configured. *owner* must own *document_id*: a create against a document
        belonging to someone else raises ``DocumentNotFoundError`` rather than
        attaching a chapter to it.
        """
        if self._document_repo is None or self._document_repo.load_shell(document_id, owner) is None:
            raise DocumentNotFoundError(document_id)
        index = self._resolve_index(document_id, after_chapter_id, owner)
        for row in self._chapter_repo.list_by_document(document_id, owner):
            if str(row.get("title") or "").lower() == title.lower():
                raise DuplicateTitleError(title)
        document_repo = self._document_repo
        if document_repo is None or document_repo.load_shell(document_id, owner) is None:
            raise DocumentNotFoundError(document_id)
        ch = Chapter(id=chapter_id, title=title, category=category, state=DataState.NEW)
        uow = self._uow_factory.get_unit_of_work()
        uow.register(ch, document_id=document_id, index=str(index), owner=owner)
        uow.commit()
        store = self._store(owner)
        if store is not None and self._document_repo is not None:
            document = self._document_repo.load_shell(document_id, owner)
            if document is not None:
                self._materialize_new_chapter(store, document, ch)
        return ch

    def _resolve_index(self, document_id: str, after_chapter_id: str | None, owner: str) -> int:
        """Return the index of a new chapter placed after *after_chapter_id*."""
        if after_chapter_id is None:
            return 0
        for row in self._chapter_repo.list_by_document(document_id, owner):
            if row["id"] == after_chapter_id:
                return int(row["index"]) + 1
        raise ChapterAfterNotFoundError(after_chapter_id)

    def _materialize_new_chapter(self, store: DocumentStore, document: Document, ch: Chapter) -> None:
        """Write the new chapter's empty owned markdown file and git-commit it."""
        content = markdown_writer.render_chapter_markdown(ch, self._nlp)
        store.write_chapter(document.title, ch.act, ch.title, content, ch.category)
        store.git_commit(document.title, f"create: chapter {ch.id[:8]}")

    def move(self, chapter_id: str, after_chapter_id: str | None, *, owner: str) -> Chapter | None:
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
        ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        if chapter_id == after_chapter_id:
            return ch
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return None
        members = self._chapter_repo.list_by_document(document_id, owner)
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
                    uow.register(ch, document_id=document_id, owner=owner)
                    uow.commit()
        self._chapter_repo.reorder(document_id, ordered_ids, owner=owner)
        return ch

    def set_pov(self, chapter_id: str, name: str, *, owner: str) -> dict[str, object] | None:
        """Set, suggest, or clear the chapter's point-of-view character.

        The matching and persistence live in :mod:`dockb.services.chapter_front_matter`."""
        ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        if document_id is None:
            return None
        document = self._document_repo.load_shell(document_id, owner) if self._document_repo is not None else None
        return apply_set_pov(
            ch,
            document_id,
            name,
            chapter_repo=self._chapter_repo,
            uow_factory=self._uow_factory,
            store=self._store(owner),
            document=document,
            owner=owner,
        )

    def renumber(self, document_id: str, *, owner: str, start: int = 1) -> list[dict[str, str]] | None:
        """Renumber every act chapter of *document_id*, from *start*, in display order.

        Chapters of category ``Chapter`` take their position in the document's
        chapter order (what the editor lists, ``PART_OF.index``) as their new
        number — counting from *start* (1 by default, 0 when the writer counts
        from zero): the number in the title is rewritten in place, any letter
        suffix goes, and a title with no number gains one at the end (see
        :mod:`dockb.chapter_numbers`). ``Character`` chapters are untouched — they
        carry no number — but their titles still count when the new titles are
        checked for duplicates, so a renumber cannot quietly walk over one. The
        whole renumber is planned before anything is written: a case-insensitive
        duplicate raises ``DuplicateTitleError`` and nothing changes. The graph titles
        are rewritten (one transaction) and the markdown files move through the store's
        own git commit; a document with no store still has its graph retitled. With both
        a graph and a store the renumber is journaled first, so a crash between the two
        leaves a record the next boot replays. The whole renumber holds the document's
        exclusive lock.

        Returns one ``{id, old_title, new_title}`` per chapter whose title
        changed, ``[]`` when nothing needed changing, and ``None`` when *owner*
        does not own such a document.
        """
        document = self._document_repo.load_shell(document_id, owner) if self._document_repo is not None else None
        if document is None:
            return None
        with self._document_locks.exclusive(document_id):
            entries, renames, moves = plan_renumber(self._chapter_repo.list_by_document(document_id, owner), start=start)
            if not entries:
                return []
            store = self._store(owner)
            if store is None:
                self._chapter_repo.retitle(document_id, entries, owner)
                return renames
            record = JournalRecord.new(
                "chapter-renumber",
                account_id=owner,
                document_id=document_id,
                payload={
                    "document_title": document.title,
                    "entries": entries,
                    "moves": [
                        {"act": move.act, "category": move.category, "old_title": move.old_title, "new_title": move.new_title}
                        for move in moves
                    ],
                },
            )
            store.journal().write(record)
            store.renumber_chapters(document.title, moves)
            self._chapter_repo.retitle(document_id, entries, owner)
            store.journal().remove(record.op_id)
            return renames

    def update(
        self,
        chapter_id: str,
        title: str,
        *,
        owner: str,
    ) -> Chapter | None:
        """Update the chapter title, renaming its owned file and refreshing the graph.

        Returns None if not found. A title change with a document store is journaled
        before anything moves: the record names the old and new titles, so a crash
        between the git mv and the graph commit is repaired at the next boot. The
        whole update holds the document's exclusive lock, so a rename never interleaves
        with a save of one of its sibling chapters.
        """
        ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return None
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        with self._document_locks.exclusive(document_id or chapter_id):
            if document_id is not None:
                for row in self._chapter_repo.list_by_document(document_id, owner):
                    if row["id"] != chapter_id and str(row.get("title") or "").lower() == title.lower():
                        raise DuplicateTitleError(title)
            old_title = ch.title
            ch.title = title
            ch.state = DataState.CHANGED
            uow = self._uow_factory.get_unit_of_work()
            uow.register(ch, document_id=document_id or "", owner=owner)
            store = self._store(owner)
            if store is None or title == old_title or document_id is None or self._document_repo is None:
                uow.commit()
                return ch
            store_document = self._document_repo.load_shell(document_id, owner)
            if store_document is None:
                uow.commit()
                return ch
            record = JournalRecord.new(
                "chapter-rename",
                account_id=owner,
                document_id=document_id,
                payload={
                    "chapter_id": chapter_id,
                    "document_title": store_document.title,
                    "act": ch.act or "",
                    "category": ch.category or "Chapter",
                    "from": old_title,
                    "to": title,
                },
            )
            store.journal().write(record)
            store.rename_chapter(store_document.title, ch.act, old_title, title, ch.category)
            uow.commit()
            store.journal().remove(record.op_id)
        return ch

    def delete(self, chapter_id: str, *, owner: str) -> bool:
        """Delete a chapter: remove its owned store file, then the graph subtree.

        The markdown file (``git rm`` + commit) goes first so a failure leaves
        the graph intact for a retry. The graph DELETED write cascades to the
        chapter's paragraphs, sentences, and tokens. Returns False if not found.
        The whole delete holds the document's exclusive lock.
        """
        ch = self._chapter_repo.load(chapter_id, owner)
        if ch is None:
            return False
        document_id = self._chapter_repo.find_document_id(chapter_id, owner)
        with self._document_locks.exclusive(document_id or chapter_id):
            store = self._store(owner)
            if store is not None and self._document_repo is not None and document_id is not None:
                document = self._document_repo.load_shell(document_id, owner)
                if document is not None:
                    store.remove_chapter(document.title, ch.act, ch.title, ch.category)
            ch.state = DataState.DELETED
            uow = self._uow_factory.get_unit_of_work()
            uow.register(ch, document_id=document_id or "", owner=owner)
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

    def list_by_chapter(self, chapter_id: str, *, owner: str) -> list[dict[str, str]]:
        """Return paragraph summaries for a chapter.

        A chapter the caller does not own lists the same as one with no paragraphs:
        an empty list.
        """
        return self._paragraph_repo.list_by_chapter(chapter_id, owner)

    def get(self, paragraph_id: str, *, owner: str) -> Paragraph | None:
        """Load a full paragraph hierarchy, or None.

        None also covers a paragraph of another account's document, so a paragraph id
        belonging to someone else is no more confirmable than one never created.
        """
        return self._paragraph_repo.load(paragraph_id, owner)

    def create(
        self,
        paragraph_id: str,
        content: list[Sentence],
        chapter_id: str,
        *,
        owner: str,
    ) -> Paragraph:
        """Create a new paragraph with content and commit it.

        The paragraph is written through its chapter, so the chapter has to be the
        caller's: a write whose ``MATCH`` matches nothing writes nothing and reports no
        error, which would answer 200 for a paragraph that does not exist. Raises
        ``ChapterNotFoundError`` instead, which the route reports as 404.
        """
        if not self._paragraph_repo.owns_chapter(chapter_id, owner):
            raise ChapterNotFoundError(chapter_id)
        para = Paragraph(id=paragraph_id, state=DataState.NEW)
        for sent in content:
            para.append_child(sent)

        if self._can_use_async():
            self._enqueue_content_jobs(para, chapter_id=chapter_id, owner=owner)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(para, chapter_id=chapter_id, owner=owner)
            uow.commit()
        return para

    def update(
        self,
        paragraph_id: str,
        content: list[Sentence],
        chapter_id: str | None = None,
        *,
        owner: str,
    ) -> Paragraph | None:
        """Replace paragraph content.  Handles sentence gain/loss.

        Returns None if the paragraph is not there for *owner* — which is also what a
        paragraph of another account's document returns.
        """
        para = self._paragraph_repo.load(paragraph_id, owner)
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
            self._enqueue_content_jobs(para, chapter_id=chapter_id or "", owner=owner)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(para, chapter_id=chapter_id or "", owner=owner)
            uow.commit()
        return para

    def delete(self, paragraph_id: str, *, owner: str) -> bool:
        """Delete a paragraph and all children.

        Returns False if the paragraph is not there for *owner*, which is also what a
        paragraph of another account's document returns.
        """
        para = self._paragraph_repo.load(paragraph_id, owner)
        if para is None:
            return False
        para.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(para, chapter_id="", owner=owner)
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

    def list_by_paragraph(self, paragraph_id: str, *, owner: str) -> list[dict[str, str]]:
        """Return sentence summaries for a paragraph.

        A paragraph the caller does not own lists the same as one with no sentences:
        an empty list.
        """
        return self._sentence_repo.list_by_paragraph(paragraph_id, owner)

    def get(self, sentence_id: str, *, owner: str) -> Sentence | None:
        """Load a full sentence with tokens, or None.

        None also covers a sentence of another account's document, so a sentence id
        belonging to someone else is no more confirmable than one never created.
        """
        return self._sentence_repo.load(sentence_id, owner)

    def create(
        self,
        sentence_id: str,
        text: str,
        paragraph_id: str,
        *,
        owner: str,
    ) -> Sentence:
        """Create a new sentence with text and commit it.

        The sentence is written through its paragraph, so the paragraph has to be the
        caller's: a write whose ``MATCH`` matches nothing writes nothing and reports no
        error, which would answer 200 for a sentence that does not exist. Raises
        ``ParagraphNotFoundError`` instead, which the route reports as 404.

        The text is set on the sentence (marking it dirty).  Tokenisation
        happens asynchronously via the job queue when a session context is
        available, or synchronously via UoW commit otherwise.
        """
        if not self._sentence_repo.owns_paragraph(paragraph_id, owner):
            raise ParagraphNotFoundError(paragraph_id)
        sent = Sentence(id=sentence_id)
        sent.set_text(text)

        if self._can_use_async():
            self._enqueue_content_jobs(sent, paragraph_id=paragraph_id, owner=owner)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(sent, paragraph_id=paragraph_id, owner=owner)
            uow.flush_pending()
        return sent

    def update(
        self,
        sentence_id: str,
        text: str,
        paragraph_id: str | None = None,
        *,
        owner: str,
    ) -> Sentence | None:
        """Replace sentence text.

        Returns None if the sentence is not there for *owner* — which is also what a
        sentence of another account's document returns.
        """
        sent = self._sentence_repo.load(sentence_id, owner)
        if sent is None:
            return None

        sent.set_text(text)

        if self._can_use_async():
            self._enqueue_content_jobs(sent, paragraph_id=paragraph_id or "", owner=owner)
        else:
            uow = self._uow_factory.get_unit_of_work()
            uow.register(sent, paragraph_id=paragraph_id or "", owner=owner)
            uow.flush_pending()
        return sent

    def delete(self, sentence_id: str, *, owner: str) -> bool:
        """Delete a sentence and all tokens.

        Returns False if the sentence is not there for *owner*, which is also what a
        sentence of another account's document returns.
        """
        sent = self._sentence_repo.load(sentence_id, owner)
        if sent is None:
            return False
        sent.state = DataState.DELETED
        uow = self._uow_factory.get_unit_of_work()
        uow.register(sent, paragraph_id="", owner=owner)
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
