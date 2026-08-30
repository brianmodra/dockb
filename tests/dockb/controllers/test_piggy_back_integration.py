"""Tests for notification piggy-back integration in mutation routes.

Verifies that POST/PUT/DELETE responses include pending notifications
from the SessionContext when one is configured, and omit them when not.
"""

# pylint: disable=unused-argument

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.chapters import router as chapters_router
from dockb.controllers.chapters import set_ch_service
from dockb.controllers.documents import router as documents_router
from dockb.controllers.documents import set_doc_service
from dockb.controllers.notifications import set_session_context
from dockb.controllers.paragraphs import router as paragraphs_router
from dockb.controllers.paragraphs import set_para_service
from dockb.controllers.sentences import router as sentences_router
from dockb.controllers.sentences import set_sent_service
from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence
from dockb.services.session_context import Notification, SessionContext

# ---------------------------------------------------------------------------
# Minimal mock services (reuse from test_routes or redefine)
# ---------------------------------------------------------------------------


class _MockDocService:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    def list_all(self) -> list[dict[str, str]]:
        return [{"id": d.id, "title": d.title, "author": d.author} for d in self._docs.values()]

    def get(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    def create(self, document_id: str, title: str, author: str) -> Document:
        doc = Document(id=document_id, title=title, author=author, state=DataState.SYNC)
        self._docs[document_id] = doc
        return doc

    def update(self, document_id: str, title: str, author: str) -> Document | None:
        doc = self._docs.get(document_id)
        if doc is None:
            return None
        doc.title = title
        doc.author = author
        return doc

    def delete(self, document_id: str) -> bool:
        return self._docs.pop(document_id, None) is not None


class _MockChService:
    def __init__(self) -> None:
        self._chapters: dict[str, Chapter] = {}

    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        return [{"id": ch.id} for ch in self._chapters.values()]

    def get(self, chapter_id: str) -> Chapter | None:
        return self._chapters.get(chapter_id)

    def create(self, chapter_id: str, title: str, document_id: str) -> Chapter:
        ch = Chapter(id=chapter_id, title=title, state=DataState.SYNC)
        self._chapters[chapter_id] = ch
        return ch

    def update(self, chapter_id: str, title: str) -> Chapter | None:
        ch = self._chapters.get(chapter_id)
        if ch is None:
            return None
        ch.title = title
        return ch

    def delete(self, chapter_id: str) -> bool:
        return self._chapters.pop(chapter_id, None) is not None


class _MockParaService:
    def __init__(self) -> None:
        self._paras: dict[str, Paragraph] = {}

    def list_by_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        return [{"id": p.id} for p in self._paras.values()]

    def get(self, paragraph_id: str) -> Paragraph | None:
        return self._paras.get(paragraph_id)

    def create(self, paragraph_id: str, content: list[Sentence], chapter_id: str) -> Paragraph:
        p = Paragraph(id=paragraph_id, state=DataState.SYNC)
        for s in content:
            p.append_child(s)
        self._paras[paragraph_id] = p
        return p

    def update(self, paragraph_id: str, content: list[Sentence], chapter_id: str | None = None) -> Paragraph | None:
        p = self._paras.get(paragraph_id)
        if p is None:
            return None
        p.clear_semantics()
        for s in content:
            p.append_child(s)
        return p

    def delete(self, paragraph_id: str) -> bool:
        return self._paras.pop(paragraph_id, None) is not None


class _MockSentService:
    def __init__(self) -> None:
        self._sentences: dict[str, Sentence] = {}

    def list_by_paragraph(self, paragraph_id: str) -> list[dict[str, str]]:
        return [{"id": s.id} for s in self._sentences.values()]

    def get(self, sentence_id: str) -> Sentence | None:
        return self._sentences.get(sentence_id)

    def create(self, sentence_id: str, text: str, paragraph_id: str) -> Sentence:
        s = Sentence(id=sentence_id, state=DataState.SYNC)
        s.set_text(text)
        self._sentences[sentence_id] = s
        return s

    def update(self, sentence_id: str, text: str, paragraph_id: str | None = None) -> Sentence | None:
        s = self._sentences.get(sentence_id)
        if s is None:
            return None
        s.set_text(text)
        return s

    def delete(self, sentence_id: str) -> bool:
        return self._sentences.pop(sentence_id, None) is not None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app(session_context: SessionContext | None = None) -> FastAPI:
    set_doc_service(_MockDocService())
    set_ch_service(_MockChService())
    set_para_service(_MockParaService())
    set_sent_service(_MockSentService())
    set_session_context(session_context)

    app = FastAPI()
    app.include_router(documents_router)
    app.include_router(chapters_router)
    app.include_router(paragraphs_router)
    app.include_router(sentences_router)
    return app


# ---------------------------------------------------------------------------
# Piggy-back tests
# ---------------------------------------------------------------------------


class TestPiggyBackDocumentMutations:
    """Notifications piggy-backed on document mutation responses."""

    def setup_method(self) -> None:
        self.ctx = SessionContext()
        self.app = _build_app(session_context=self.ctx)
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_session_context(None)

    def test_create_document_no_notifications(self) -> None:
        resp = self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] is None

    def test_create_document_with_pending_notification(self) -> None:
        self.ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        resp = self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] is not None
        assert len(data["notifications"]) == 1
        assert data["notifications"][0]["type"] == "sentence_split"

    def test_notifications_cleared_after_piggyback(self) -> None:
        self.ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        # Second mutation — no notifications left
        resp = self.client.post("/api/documents", json={"attrs": {"id": "d2", "title": "T2", "author": "A2"}})
        assert resp.json()["notifications"] is None

    def test_delete_document_with_notification(self) -> None:
        self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        self.ctx.add_notification(Notification(type="paragraph_split", payload={"chapter_id": "ch1"}))
        resp = self.client.delete("/api/documents/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] is not None
        assert data["notifications"][0]["type"] == "paragraph_split"


class TestPiggyBackChapterMutations:
    """Notifications piggy-backed on chapter mutation responses."""

    def setup_method(self) -> None:
        self.ctx = SessionContext()
        self.app = _build_app(session_context=self.ctx)
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_session_context(None)

    def test_create_chapter_with_notification(self) -> None:
        self.ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        resp = self.client.post(
            "/api/chapters",
            json={"attrs": {"id": "c1", "title": "Ch1"}, "relations": {"document_id": "d1"}},
        )
        assert resp.status_code == 200
        assert resp.json()["notifications"] is not None

    def test_update_chapter_with_notification(self) -> None:
        self.client.post(
            "/api/chapters",
            json={"attrs": {"id": "c1", "title": "Old"}, "relations": {"document_id": "d1"}},
        )
        self.ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        resp = self.client.put("/api/chapters/c1", json={"attrs": {"title": "New"}})
        assert resp.status_code == 200
        assert resp.json()["notifications"] is not None


class TestPiggyBackNoSessionContext:
    """When no SessionContext is configured, no notifications in responses."""

    def setup_method(self) -> None:
        self.app = _build_app(session_context=None)
        self.client = TestClient(self.app)

    def test_create_document_no_notifications(self) -> None:
        resp = self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        assert resp.status_code == 200
        assert resp.json()["notifications"] is None

    def test_delete_document_no_notifications(self) -> None:
        self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        resp = self.client.delete("/api/documents/d1")
        assert resp.status_code == 200
        assert resp.json()["notifications"] is None


class TestPiggyBackMultipleNotifications:
    """Multiple notifications delivered in one response."""

    def setup_method(self) -> None:
        self.ctx = SessionContext()
        self.app = _build_app(session_context=self.ctx)
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_session_context(None)

    def test_two_notifications_in_response(self) -> None:
        self.ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        self.ctx.add_notification(Notification(type="paragraph_split", payload={"chapter_id": "ch1"}))
        resp = self.client.post("/api/documents", json={"attrs": {"id": "d1", "title": "T", "author": "A"}})
        data = resp.json()
        assert data["notifications"] is not None
        assert len(data["notifications"]) == 2
