"""Composition root — wires infrastructure to route-level DI globals.

``wire()`` is called once at startup after the ``SessionFactory`` is ready.
``unwire()`` is called at shutdown to tear down all DI globals.
"""

# pylint: disable=invalid-name,global-statement

from __future__ import annotations

import os
import secrets
import subprocess
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import spacy

from dockb.controllers.auth import set_auth_service
from dockb.controllers.chapters import set_ch_service
from dockb.controllers.documents import set_doc_service
from dockb.controllers.history import set_history_service
from dockb.controllers.notifications import set_session_context
from dockb.controllers.paragraphs import set_para_service
from dockb.controllers.sentences import set_sent_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.document_store import DocumentStore
from dockb.infrastructure.history.snapshot_reader import SnapshotReader
from dockb.infrastructure.neo4j.unit_of_work_factory import UnitOfWorkFactory
from dockb.infrastructure.oauth.factory import providers_from_env
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.document_repository import DocumentRepository
from dockb.repositories.paragraph_repository import ParagraphRepository
from dockb.repositories.sentence_repository import SentenceRepository
from dockb.services.auth_service import AuthService
from dockb.services.crud_services import ChapterService, DocumentService, ParagraphService, SentenceService
from dockb.services.history_service import HistoryService
from dockb.services.session_context import SessionContext

_stack: ExitStack | None = None

_DOCUMENTS_DIR_NAME = "dockb_chapters_dir"


def resolve_document_base_dir(base_dir: Path | None = None) -> Path:
    """Return the effective server-owned markdown base directory, provisioning it.

    Defaults to ``cwd/dockb_chapters_dir`` when neither ``DOCKB_CHAPTERS_DIR``
    nor *base_dir* is set. A missing directory is created, and a directory that
    is not yet a git repository is ``git init``-ed — the document store owns
    the repo (its ``git_commit`` requires one).
    """
    if base_dir is not None:
        base = Path(base_dir)
    else:
        configured = os.environ.get("DOCKB_CHAPTERS_DIR")
        if configured:
            base = Path(configured)
        else:
            base = Path.cwd() / _DOCUMENTS_DIR_NAME
    if not (base / ".git").is_dir():
        base.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=str(base),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return base


def _build_auth_service(document_base_dir: Path) -> AuthService:
    """Build the AuthService wired for *document_base_dir*.

    With ``DOCKB_SECRET_KEY`` set the configured OAuth providers (id + secret
    pairs) enable the login flow. Without a secret there is nothing to sign
    cookies or encrypt tokens with, so the backend runs in **local mode**: the
    identity is the OS username, no login is required, and an ephemeral key is
    used in memory (nothing is signed or encrypted in local mode).
    """
    secret = os.environ.get("DOCKB_SECRET_KEY")
    providers = providers_from_env() if secret is not None else {}
    if secret is None:
        secret = secrets.token_hex(32)
    return AuthService(
        providers=providers,
        pending_store=PendingLoginStore(),
        account_store=AccountStore(base_dir=document_base_dir, secret=secret),
        session_manager=SessionManager(),
        signer=SessionSigner(
            secret,
            ttl_hours=int(os.environ.get("OAUTH_SESSION_TTL_HOURS", "48")),
        ),
    )


def wire(  # pylint: disable=too-many-locals
    session_factory: Any,
    *,
    snapshot_base_dir: Path | None = None,
    document_base_dir: Path | None = None,
    accounts_base_dir: Path | None = None,
) -> SessionContext:
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

    document_store = DocumentStore(base_dir=document_base_dir) if document_base_dir is not None else None
    nlp = spacy.load("en_core_web_sm") if (document_base_dir is not None or snapshot_base_dir is not None) else None
    doc_svc = DocumentService(uow_factory=uow_factory, document_repo=repos[Document], document_store=document_store, nlp=nlp)
    ch_svc = ChapterService(
        uow_factory=uow_factory,
        chapter_repo=repos[Chapter],
        document_repo=repos[Document],
        document_store=document_store,
        nlp=nlp,
    )
    para_svc = ParagraphService(uow_factory=uow_factory, paragraph_repo=repos[Paragraph])
    sent_svc = SentenceService(uow_factory=uow_factory, sentence_repo=repos[Sentence])

    ctx = SessionContext()

    set_doc_service(doc_svc)
    set_ch_service(ch_svc)
    set_para_service(para_svc)
    set_sent_service(sent_svc)
    set_session_context(ctx)

    if snapshot_base_dir is not None:
        assert nlp is not None
        reader = SnapshotReader(base_dir=snapshot_base_dir, nlp=nlp)
        history_svc = HistoryService(reader=reader, chapter_repo=repos[Chapter], uow_factory=uow_factory)
        set_history_service(history_svc)

    auth_base_dir = accounts_base_dir if accounts_base_dir is not None else document_base_dir
    if auth_base_dir is not None:
        set_auth_service(_build_auth_service(auth_base_dir))

    return ctx


def unwire() -> None:
    """Clear all route-level DI globals and release resources."""
    global _stack  # noqa: PLW0603
    set_auth_service(None)
    set_doc_service(None)
    set_ch_service(None)
    set_para_service(None)
    set_sent_service(None)
    set_session_context(None)
    set_history_service(None)
    if _stack is not None:
        _stack.close()
        _stack = None
