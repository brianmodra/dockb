"""Composition root — wires infrastructure to route-level DI globals.

``wire()`` is called once at startup after the ``SessionFactory`` is ready.
``unwire()`` is called at shutdown to tear down all DI globals.
"""

# pylint: disable=invalid-name,global-statement

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any

from dockb.controllers.chapters import set_ch_service
from dockb.controllers.documents import set_doc_service
from dockb.controllers.history import set_history_service
from dockb.controllers.notifications import set_session_context
from dockb.controllers.paragraphs import set_para_service
from dockb.controllers.sentences import set_sent_service
from dockb.infrastructure.history.snapshot_reader import SnapshotReader
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.crud_services import ChapterService, DocumentService, ParagraphService, SentenceService
from dockb.services.history_service import HistoryService
from dockb.services.session_context import SessionContext

_stack: ExitStack | None = None


def wire(session_factory: Any, *, snapshot_base_dir: Path | None = None) -> SessionContext:
    """Wire repositories, services, and session context to route DI globals.

    Returns the created SessionContext for use by the caller (e.g. startup
    needs it to pass to the JobQueue / DocCache wiring later).
    """
    global _stack  # noqa: PLW0603
    _stack = ExitStack()
    session = _stack.enter_context(session_factory.session())

    repos: dict[type, Any] = {
        Document: DocumentRepository(session),
        Chapter: ChapterRepository(session),
        Paragraph: ParagraphRepository(session),
        Sentence: SentenceRepository(session),
    }

    uow_factory = UnitOfWorkFactory(
        repos=repos,
        session_factory=session_factory,
        reconstructor=None,
    )

    doc_svc = DocumentService(uow_factory=uow_factory, document_repo=repos[Document])
    ch_svc = ChapterService(uow_factory=uow_factory, chapter_repo=repos[Chapter])
    para_svc = ParagraphService(uow_factory=uow_factory, paragraph_repo=repos[Paragraph])
    sent_svc = SentenceService(uow_factory=uow_factory, sentence_repo=repos[Sentence])

    ctx = SessionContext()

    set_doc_service(doc_svc)
    set_ch_service(ch_svc)
    set_para_service(para_svc)
    set_sent_service(sent_svc)
    set_session_context(ctx)

    if snapshot_base_dir is not None:
        reader = SnapshotReader(base_dir=snapshot_base_dir)
        history_svc = HistoryService(reader=reader, chapter_repo=repos[Chapter], uow_factory=uow_factory)
        set_history_service(history_svc)

    return ctx


def unwire() -> None:
    """Clear all route-level DI globals and release resources."""
    global _stack  # noqa: PLW0603
    set_doc_service(None)
    set_ch_service(None)
    set_para_service(None)
    set_sent_service(None)
    set_session_context(None)
    set_history_service(None)
    if _stack is not None:
        _stack.close()
        _stack = None
