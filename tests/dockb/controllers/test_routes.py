"""Tests for FastAPI route handlers.

Uses mocked services and ``TestClient`` — no Neo4j required.
"""

# pylint: disable=unused-argument

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.models.base import DataState
from dockb.models.chapter import Chapter
from dockb.models.document import Document
from dockb.models.paragraph import Paragraph
from dockb.models.sentence import Sentence

# ---------------------------------------------------------------------------
# Helpers: mock services
# ---------------------------------------------------------------------------


def _make_doc(doc_id: str = "d1", title: str = "Test", author: str = "A") -> Document:
    return Document(id=doc_id, title=title, author=author, state=DataState.SYNC)


def _make_chapter(ch_id: str = "c1", title: str = "Ch1") -> Chapter:
    return Chapter(id=ch_id, title=title, state=DataState.SYNC)


def _make_paragraph(p_id: str = "p1") -> Paragraph:
    return Paragraph(id=p_id, state=DataState.SYNC)


def _make_sentence(s_id: str = "s1", text: str = "Hello.") -> Sentence:
    s = Sentence(id=s_id, state=DataState.SYNC)
    s.set_text(text)
    return s


class MockDocumentService:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}

    def list_all(self) -> list[dict[str, str]]:
        return [{"id": d.id, "title": d.title, "author": d.author} for d in self._docs.values()]

    def get(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    def create(self, document_id: str, title: str, author: str) -> Document:
        doc = _make_doc(document_id, title, author)
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


class MockChapterService:
    def __init__(self) -> None:
        self._chapters: dict[str, Chapter] = {}

    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        return [{"id": ch.id} for ch in self._chapters.values()]

    def get(self, chapter_id: str) -> Chapter | None:
        return self._chapters.get(chapter_id)

    def create(self, chapter_id: str, title: str, document_id: str) -> Chapter:
        ch = _make_chapter(chapter_id, title)
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


class MockParagraphService:
    def __init__(self) -> None:
        self._paragraphs: dict[str, Paragraph] = {}

    def list_by_chapter(self, chapter_id: str) -> list[dict[str, str]]:
        return [{"id": p.id} for p in self._paragraphs.values()]

    def get(self, paragraph_id: str) -> Paragraph | None:
        return self._paragraphs.get(paragraph_id)

    def create(self, paragraph_id: str, content: list[Sentence], chapter_id: str) -> Paragraph:
        p = _make_paragraph(paragraph_id)
        for s in content:
            p.append_child(s)
        self._paragraphs[paragraph_id] = p
        return p

    def update(self, paragraph_id: str, content: list[Sentence], chapter_id: str | None = None) -> Paragraph | None:
        p = self._paragraphs.get(paragraph_id)
        if p is None:
            return None
        for s in content:
            p.append_child(s)
        return p

    def delete(self, paragraph_id: str) -> bool:
        return self._paragraphs.pop(paragraph_id, None) is not None


class MockSentenceService:
    def __init__(self) -> None:
        self._sentences: dict[str, Sentence] = {}

    def list_by_paragraph(self, paragraph_id: str) -> list[dict[str, str]]:
        return [{"id": s.id} for s in self._sentences.values()]

    def get(self, sentence_id: str) -> Sentence | None:
        return self._sentences.get(sentence_id)

    def create(self, sentence_id: str, text: str, paragraph_id: str) -> Sentence:
        s = _make_sentence(sentence_id, text)
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


def _build_app(
    doc_svc: MockDocumentService | None = None,
    ch_svc: MockChapterService | None = None,
    para_svc: MockParagraphService | None = None,
    sent_svc: MockSentenceService | None = None,
) -> FastAPI:
    from dockb.controllers.chapters import router as chapters_router
    from dockb.controllers.chapters import set_ch_service
    from dockb.controllers.documents import router as documents_router
    from dockb.controllers.documents import set_doc_service
    from dockb.controllers.paragraphs import router as paragraphs_router
    from dockb.controllers.paragraphs import set_para_service
    from dockb.controllers.sentences import router as sentences_router
    from dockb.controllers.sentences import set_sent_service

    set_doc_service(doc_svc or MockDocumentService())
    set_ch_service(ch_svc or MockChapterService())
    set_para_service(para_svc or MockParagraphService())
    set_sent_service(sent_svc or MockSentenceService())

    app = FastAPI()
    app.include_router(documents_router)
    app.include_router(chapters_router)
    app.include_router(paragraphs_router)
    app.include_router(sentences_router)
    return app


# ---------------------------------------------------------------------------
# Document routes
# ---------------------------------------------------------------------------


class TestDocumentRoutes:
    def setup_method(self) -> None:
        self.svc = MockDocumentService()
        self.app = _build_app(doc_svc=self.svc)
        self.client = TestClient(self.app)

    def test_list_documents_empty(self) -> None:
        resp = self.client.get("/api/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_documents(self) -> None:
        self.svc.create("d1", "T1", "A1")
        resp = self.client.get("/api/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["attrs"]["id"] == "d1"
        assert data[0]["attrs"]["title"] == "T1"
        assert data[0]["attrs"]["author"] == "A1"
        assert data[0]["chapter_summaries"] == []

    def test_get_document_not_found(self) -> None:
        resp = self.client.get("/api/documents/nonexistent")
        assert resp.status_code == 404

    def test_get_document(self) -> None:
        self.svc.create("d1", "Faith", "Paul")
        resp = self.client.get("/api/documents/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["attrs"]["id"] == "d1"
        assert data["attrs"]["title"] == "Faith"
        assert data["attrs"]["author"] == "Paul"
        assert data["chapter_summaries"] == []

    def test_create_document(self) -> None:
        resp = self.client.post(
            "/api/documents",
            json={"attrs": {"id": "d1", "title": "T", "author": "A"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["code"] == "ok"
        assert data["status"]["message"] == "success"

    def test_create_document_requires_id(self) -> None:
        resp = self.client.post(
            "/api/documents",
            json={"attrs": {"title": "T", "author": "A"}},
        )
        assert resp.status_code == 422

    def test_update_document(self) -> None:
        self.svc.create("d1", "Old", "Old")
        resp = self.client.put(
            "/api/documents/d1",
            json={"attrs": {"title": "New", "author": "New"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["code"] == "ok"

    def test_update_document_not_found(self) -> None:
        resp = self.client.put(
            "/api/documents/nonexistent",
            json={"attrs": {"title": "T", "author": "A"}},
        )
        assert resp.status_code == 404

    def test_delete_document(self) -> None:
        self.svc.create("d1", "T", "A")
        resp = self.client.delete("/api/documents/d1")
        assert resp.status_code == 200
        assert resp.json()["status"]["code"] == "ok"

    def test_delete_document_not_found(self) -> None:
        resp = self.client.delete("/api/documents/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Chapter routes
# ---------------------------------------------------------------------------


class TestChapterRoutes:
    def setup_method(self) -> None:
        self.doc_svc = MockDocumentService()
        self.ch_svc = MockChapterService()
        self.app = _build_app(doc_svc=self.doc_svc, ch_svc=self.ch_svc)
        self.client = TestClient(self.app)

    def test_list_chapters_empty(self) -> None:
        resp = self.client.get("/api/chapters", params={"document": "d1"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_chapter_not_found(self) -> None:
        resp = self.client.get("/api/chapters/nonexistent")
        assert resp.status_code == 404

    def test_get_chapter(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        resp = self.client.get("/api/chapters/c1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "chapter"
        assert data["attrs"]["id"] == "c1"
        assert data["attrs"]["title"] == "Intro"
        assert data["content"] == []

    def test_create_chapter(self) -> None:
        resp = self.client.post(
            "/api/chapters",
            json={
                "attrs": {"id": "c1", "title": "Ch1"},
                "relations": {"document_id": "d1"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"]["code"] == "ok"

    def test_update_chapter(self) -> None:
        self.ch_svc.create("c1", "Old", "d1")
        resp = self.client.put(
            "/api/chapters/c1",
            json={"attrs": {"title": "New"}},
        )
        assert resp.status_code == 200

    def test_update_chapter_not_found(self) -> None:
        resp = self.client.put(
            "/api/chapters/nonexistent",
            json={"attrs": {"title": "T"}},
        )
        assert resp.status_code == 404

    def test_delete_chapter(self) -> None:
        self.ch_svc.create("c1", "T", "d1")
        resp = self.client.delete("/api/chapters/c1")
        assert resp.status_code == 200

    def test_delete_chapter_not_found(self) -> None:
        resp = self.client.delete("/api/chapters/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Paragraph routes
# ---------------------------------------------------------------------------


class TestParagraphRoutes:
    def setup_method(self) -> None:
        self.ch_svc = MockChapterService()
        self.para_svc = MockParagraphService()
        self.app = _build_app(ch_svc=self.ch_svc, para_svc=self.para_svc)
        self.client = TestClient(self.app)

    def test_list_paragraphs_empty(self) -> None:
        resp = self.client.get("/api/paragraphs", params={"chapter": "c1"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_paragraph_not_found(self) -> None:
        resp = self.client.get("/api/paragraphs/nonexistent")
        assert resp.status_code == 404

    def test_get_paragraph(self) -> None:
        s = _make_sentence("s1", "Hello world.")
        self.para_svc.create("p1", [s], "c1")
        resp = self.client.get("/api/paragraphs/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "paragraph"
        assert data["attrs"]["id"] == "p1"
        assert len(data["content"]) == 1

    def test_create_paragraph(self) -> None:
        resp = self.client.post(
            "/api/paragraphs",
            json={
                "attrs": {"id": "p1"},
                "content": [
                    {
                        "type": "sentence",
                        "attrs": {"id": "s1"},
                        "content": [{"type": "text", "text": "Hello."}],
                    }
                ],
                "relations": {"chapter_id": "c1"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"]["code"] == "ok"

    def test_update_paragraph(self) -> None:
        s = _make_sentence("s1", "Old.")
        self.para_svc.create("p1", [s], "c1")
        resp = self.client.put(
            "/api/paragraphs/p1",
            json={
                "attrs": {},
                "content": [
                    {
                        "type": "sentence",
                        "attrs": {"id": "s2"},
                        "content": [{"type": "text", "text": "New."}],
                    }
                ],
            },
        )
        assert resp.status_code == 200

    def test_update_paragraph_not_found(self) -> None:
        resp = self.client.put(
            "/api/paragraphs/nonexistent",
            json={
                "attrs": {},
                "content": [
                    {
                        "type": "sentence",
                        "attrs": {"id": "s1"},
                        "content": [{"type": "text", "text": "X"}],
                    }
                ],
            },
        )
        assert resp.status_code == 404

    def test_delete_paragraph(self) -> None:
        self.para_svc.create("p1", [], "c1")
        resp = self.client.delete("/api/paragraphs/p1")
        assert resp.status_code == 200

    def test_delete_paragraph_not_found(self) -> None:
        resp = self.client.delete("/api/paragraphs/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Sentence routes
# ---------------------------------------------------------------------------


class TestSentenceRoutes:
    def setup_method(self) -> None:
        self.para_svc = MockParagraphService()
        self.sent_svc = MockSentenceService()
        self.app = _build_app(para_svc=self.para_svc, sent_svc=self.sent_svc)
        self.client = TestClient(self.app)

    def test_list_sentences_empty(self) -> None:
        resp = self.client.get("/api/sentences", params={"paragraph": "p1"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_sentence_not_found(self) -> None:
        resp = self.client.get("/api/sentences/nonexistent")
        assert resp.status_code == 404

    def test_get_sentence(self) -> None:
        self.sent_svc.create("s1", "Hello.", "p1")
        resp = self.client.get("/api/sentences/s1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "sentence"
        assert data["attrs"]["id"] == "s1"
        assert len(data["content"]) == 1
        assert data["content"][0]["text"] == "Hello."

    def test_create_sentence(self) -> None:
        resp = self.client.post(
            "/api/sentences",
            json={
                "attrs": {"id": "s1"},
                "content": [{"type": "text", "text": "First sentence."}],
                "relations": {"paragraph_id": "p1"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"]["code"] == "ok"

    def test_update_sentence(self) -> None:
        self.sent_svc.create("s1", "Old.", "p1")
        resp = self.client.put(
            "/api/sentences/s1",
            json={
                "attrs": {},
                "content": [{"type": "text", "text": "New."}],
            },
        )
        assert resp.status_code == 200

    def test_update_sentence_not_found(self) -> None:
        resp = self.client.put(
            "/api/sentences/nonexistent",
            json={"attrs": {}, "content": [{"type": "text", "text": "T"}]},
        )
        assert resp.status_code == 404

    def test_delete_sentence(self) -> None:
        self.sent_svc.create("s1", "T", "p1")
        resp = self.client.delete("/api/sentences/s1")
        assert resp.status_code == 200

    def test_delete_sentence_not_found(self) -> None:
        resp = self.client.delete("/api/sentences/nonexistent")
        assert resp.status_code == 404
