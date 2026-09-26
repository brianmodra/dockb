"""Tests for FastAPI route handlers.

Uses mocked services and ``TestClient`` — no Neo4j required.
"""

# pylint: disable=unused-argument

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.exceptions import ChapterAfterNotFoundError, DuplicateTitleError
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

    def open(self, document_id: str) -> Document | None:
        return self._docs.get(document_id)

    def create(self, document_id: str, title: str, author: str) -> Document:
        if any(d.title == title for d in self._docs.values()):
            raise DuplicateTitleError(title)
        doc = _make_doc(document_id, title, author)
        self._docs[document_id] = doc
        return doc

    def update(self, document_id: str, title: str, author: str) -> Document | None:
        doc = self._docs.get(document_id)
        if doc is None:
            return None
        for other_id, other in self._docs.items():
            if other_id != document_id and other.title.lower() == title.lower():
                raise DuplicateTitleError(title)
        doc.title = title
        doc.author = author
        return doc

    def delete(self, document_id: str) -> bool:
        return self._docs.pop(document_id, None) is not None


class MockChapterService:
    def __init__(self) -> None:
        self._chapters: dict[str, Chapter] = {}
        self._owners: dict[str, str] = {}
        self._documents: dict[str, str] = {}

    def list_by_document(self, document_id: str) -> list[dict[str, str]]:
        return [{"id": ch.id, "title": ch.title, "act": ch.act} for ch in self._chapters.values()]

    def get(self, chapter_id: str) -> Chapter | None:
        return self._chapters.get(chapter_id)

    def open(self, chapter_id: str) -> Chapter | None:
        return self._chapters.get(chapter_id)

    def create(self, chapter_id: str, title: str, document_id: str, after_chapter_id: str | None = None) -> Chapter:
        for ch_id, ch in self._chapters.items():
            if self._owners.get(ch_id) == document_id and ch.title.lower() == title.lower():
                raise DuplicateTitleError(title)
        ch = _make_chapter(chapter_id, title)
        self._chapters[chapter_id] = ch
        self._owners[chapter_id] = document_id
        return ch

    def update(self, chapter_id: str, title: str) -> Chapter | None:
        ch = self._chapters.get(chapter_id)
        if ch is None:
            return None
        owner = self._owners.get(chapter_id)
        for ch_id, other in self._chapters.items():
            if ch_id != chapter_id and other.title.lower() == title.lower() and self._owners.get(ch_id) == owner:
                raise DuplicateTitleError(title)
        ch.title = title
        return ch

    def delete(self, chapter_id: str) -> bool:
        return self._chapters.pop(chapter_id, None) is not None

    def move(self, chapter_id: str, after_chapter_id: str | None) -> Chapter | None:
        if chapter_id not in self._chapters:
            return None
        if after_chapter_id is not None and after_chapter_id not in self._chapters:
            raise ChapterAfterNotFoundError(after_chapter_id)
        return self._chapters[chapter_id]

    def open_document(self, chapter_id: str) -> str | None:
        if chapter_id not in self._chapters:
            return None
        return self._documents.setdefault(chapter_id, "# New\n")

    def save_document(self, chapter_id: str, content: str) -> SimpleNamespace:
        if chapter_id not in self._chapters:
            return None
        self._documents[chapter_id] = content
        return SimpleNamespace(
            content=content,
            summary=SimpleNamespace(created=False, changed=1, added=0, deleted=0),
        )


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

    def test_create_document_duplicate_title_conflict(self) -> None:
        self.svc.create("d1", "T", "A")
        resp = self.client.post(
            "/api/documents",
            json={"attrs": {"id": "d2", "title": "T", "author": "A"}},
        )
        assert resp.status_code == 409

    def test_update_document(self) -> None:
        self.svc.create("d1", "Old", "Old")
        resp = self.client.put(
            "/api/documents/d1",
            json={"attrs": {"title": "New", "author": "New"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["code"] == "ok"

    def test_update_document_duplicate_title_conflict(self) -> None:
        self.svc.create("d1", "Alpha", "A")
        self.svc.create("d2", "Beta", "B")
        resp = self.client.put(
            "/api/documents/d2",
            json={"attrs": {"title": "ALPHA", "author": "B"}},
        )
        assert resp.status_code == 409

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


class TestChapterRoutes:  # pylint: disable=too-many-public-methods
    def setup_method(self) -> None:
        self.doc_svc = MockDocumentService()
        self.ch_svc = MockChapterService()
        self.app = _build_app(doc_svc=self.doc_svc, ch_svc=self.ch_svc)
        self.client = TestClient(self.app)

    def test_list_chapters_empty(self) -> None:
        resp = self.client.get("/api/chapters", params={"document": "d1"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_chapters_carries_act(self) -> None:
        ch = Chapter(id="c1", title="Intro", act="Act I")
        self.ch_svc._chapters["c1"] = ch
        resp = self.client.get("/api/chapters", params={"document": "d1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data == [{"id": "c1", "title": "Intro", "act": "Act I"}]

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

    def test_get_chapter_carries_act(self) -> None:
        ch = Chapter(id="c1", title="Intro", act="Act I")
        self.ch_svc._chapters["c1"] = ch
        resp = self.client.get("/api/chapters/c1")
        assert resp.status_code == 200
        assert resp.json()["attrs"]["act"] == "Act I"

    def test_get_chapter_calls_open(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        with patch.object(self.ch_svc, "open", wraps=self.ch_svc.open) as open_mock:
            self.client.get("/api/chapters/c1")
            open_mock.assert_called_once_with("c1")

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

    def test_create_chapter_duplicate_title_conflict(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        resp = self.client.post(
            "/api/chapters",
            json={
                "attrs": {"id": "c2", "title": "INTRO"},
                "relations": {"document_id": "d1"},
            },
        )
        assert resp.status_code == 409

    def test_create_chapter_passes_after_chapter_id(self) -> None:
        with patch.object(self.ch_svc, "create", wraps=self.ch_svc.create) as create_mock:
            resp = self.client.post(
                "/api/chapters",
                json={
                    "attrs": {"id": "c2", "title": "Ch2"},
                    "relations": {"document_id": "d1", "after_chapter_id": "c1"},
                },
            )
        assert resp.status_code == 200
        create_mock.assert_called_once_with(
            chapter_id="c2",
            title="Ch2",
            document_id="d1",
            after_chapter_id="c1",
        )

    def test_create_chapter_after_not_found(self) -> None:
        with patch.object(self.ch_svc, "create", side_effect=ChapterAfterNotFoundError("ghost")):
            resp = self.client.post(
                "/api/chapters",
                json={
                    "attrs": {"id": "c2", "title": "Ch2"},
                    "relations": {"document_id": "d1", "after_chapter_id": "ghost"},
                },
            )
        assert resp.status_code == 404

    def test_update_chapter(self) -> None:
        self.ch_svc.create("c1", "Old", "d1")
        resp = self.client.put(
            "/api/chapters/c1",
            json={"attrs": {"title": "New"}},
        )
        assert resp.status_code == 200

    def test_update_chapter_duplicate_title_conflict(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        self.ch_svc.create("c2", "Body", "d1")
        resp = self.client.put(
            "/api/chapters/c2",
            json={"attrs": {"title": "INTRO"}},
        )
        assert resp.status_code == 409

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

    def test_reorder_chapter(self) -> None:
        self.ch_svc.create("c1", "Ch1", "d1")
        self.ch_svc.create("c3", "Ch3", "d1")
        with patch.object(self.ch_svc, "move", wraps=self.ch_svc.move) as move_mock:
            resp = self.client.post(
                "/api/chapters/c3/reorder",
                json={"after_chapter_id": "c1"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"]["code"] == "ok"
        move_mock.assert_called_once_with(chapter_id="c3", after_chapter_id="c1")

    def test_reorder_chapter_first(self) -> None:
        self.ch_svc.create("c1", "Ch1", "d1")
        self.ch_svc.create("c2", "Ch2", "d1")
        with patch.object(self.ch_svc, "move", wraps=self.ch_svc.move) as move_mock:
            resp = self.client.post(
                "/api/chapters/c2/reorder",
                json={"after_chapter_id": None},
            )
        assert resp.status_code == 200
        move_mock.assert_called_once_with(chapter_id="c2", after_chapter_id=None)

    def test_reorder_chapter_not_found(self) -> None:
        resp = self.client.post(
            "/api/chapters/nonexistent/reorder",
            json={"after_chapter_id": None},
        )
        assert resp.status_code == 404

    def test_reorder_after_unknown_chapter(self) -> None:
        self.ch_svc.create("c1", "Ch1", "d1")
        resp = self.client.post(
            "/api/chapters/c1/reorder",
            json={"after_chapter_id": "ghost"},
        )
        assert resp.status_code == 404

    def test_get_chapter_document(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        resp = self.client.get("/api/chapters/c1/document")
        assert resp.status_code == 200
        assert resp.json() == {"content": "# New\n", "summary": None}

    def test_get_chapter_document_not_found(self) -> None:
        resp = self.client.get("/api/chapters/nonexistent/document")
        assert resp.status_code == 404

    def test_put_chapter_document(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        resp = self.client.put("/api/chapters/c1/document", json={"content": "## Body\n"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "## Body\n"
        assert data["summary"]["created"] is False
        assert data["summary"]["changed"] == 1
        assert data["summary"]["added"] == 0
        assert data["summary"]["deleted"] == 0

    def test_put_chapter_document_not_found(self) -> None:
        resp = self.client.put("/api/chapters/nonexistent/document", json={"content": "x"})
        assert resp.status_code == 404

    def test_put_chapter_document_requires_content(self) -> None:
        self.ch_svc.create("c1", "Intro", "d1")
        resp = self.client.put("/api/chapters/c1/document", json={})
        assert resp.status_code == 422


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
