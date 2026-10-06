"""Every manuscript route acts on the caller's account, and nothing else.

These tests drive each route through a service stub that behaves as the graph does when
the named resource belongs to somebody else: it reports the resource as absent. Two
things are being held at once, and both matter:

* the route passes the signed-in account to the service — the service is the only thing
  that can scope a query, and a route that forgets hands the service no account to scope
  by, which is worse than failing loudly;
* a resource the caller does not own answers exactly as one that never existed (404, or
  an empty list), so a caller cannot use the API to discover that another account's
  chapter exists.

The services are stubs on purpose. Whether the Cypher really carries the account is the
repository layer's job, tested there; this is about the wiring from the session to the
service, which nothing else covers.
"""

# pylint: disable=too-few-public-methods,unused-argument

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers import chapters, documents, history, imports, paragraphs, sentences
from dockb.controllers.auth import get_auth_service, get_current_user
from dockb.exceptions import ChapterNotFoundError, DocumentNotFoundError, ParagraphNotFoundError
from dockb.services.markdown_import import ChapterImportSummary

_OWNER = "acct-1"


class _Recording:
    """A service stand-in that records its calls and reports every resource absent."""

    def __init__(self, absent_error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._absent_error = absent_error

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append({"method": name, **kwargs})
        if self._absent_error is not None:
            raise self._absent_error


class StubDocumentService(_Recording):
    def list_all(self, owner: str = "") -> list[dict[str, str]]:
        self._record("list_all", owner=owner)
        return []

    def create(self, document_id: str, title: str, author: str, owner: str = "") -> None:
        self._record("create", owner=owner, document_id=document_id)

    def open(self, document_id: str, owner: str = "") -> None:
        self._record("open", owner=owner, document_id=document_id)

    def update(self, document_id: str, title: str, author: str, owner: str = "") -> None:
        self._record("update", owner=owner, document_id=document_id)

    def delete(self, document_id: str, owner: str = "") -> bool:
        self._record("delete", owner=owner, document_id=document_id)
        return False


class StubChapterService(_Recording):
    def __init__(self) -> None:
        super().__init__()
        self._reorders: list[dict[str, Any]] = []

    def list_by_document(self, document_id: str, owner: str = "") -> list[dict[str, Any]]:
        self._record("list_by_document", owner=owner, document_id=document_id)
        return []

    def create(self, chapter_id: str, title: str, document_id: str, owner: str = "", **kwargs: Any) -> None:
        self._record("create", owner=owner, chapter_id=chapter_id, document_id=document_id)
        raise DocumentNotFoundError(document_id)

    def open(self, chapter_id: str, owner: str = "") -> None:
        self._record("open", owner=owner, chapter_id=chapter_id)

    def open_document(self, chapter_id: str, owner: str = "") -> None:
        self._record("open_document", owner=owner, chapter_id=chapter_id)

    def save_document(self, chapter_id: str, content: str, owner: str = "") -> None:
        self._record("save_document", owner=owner, chapter_id=chapter_id)

    def move(self, chapter_id: str, after_chapter_id: str | None, owner: str = "") -> None:
        self._record("move", owner=owner, chapter_id=chapter_id)

    def update(self, chapter_id: str, title: str, owner: str = "") -> None:
        self._record("update", owner=owner, chapter_id=chapter_id)

    def delete(self, chapter_id: str, owner: str = "") -> bool:
        self._record("delete", owner=owner, chapter_id=chapter_id)
        return False


class StubParagraphService(_Recording):
    def list_by_chapter(self, chapter_id: str, owner: str = "") -> list[dict[str, str]]:
        self._record("list_by_chapter", owner=owner, chapter_id=chapter_id)
        return []

    def create(self, paragraph_id: str, content: Any, chapter_id: str, owner: str = "") -> None:
        self._record("create", owner=owner, paragraph_id=paragraph_id, chapter_id=chapter_id)
        raise ChapterNotFoundError(chapter_id)

    def get(self, paragraph_id: str, owner: str = "") -> None:
        self._record("get", owner=owner, paragraph_id=paragraph_id)

    def update(self, paragraph_id: str, content: Any, chapter_id: str | None = None, owner: str = "") -> None:
        self._record("update", owner=owner, paragraph_id=paragraph_id)

    def delete(self, paragraph_id: str, owner: str = "") -> bool:
        self._record("delete", owner=owner, paragraph_id=paragraph_id)
        return False


class StubSentenceService(_Recording):
    def list_by_paragraph(self, paragraph_id: str, owner: str = "") -> list[dict[str, str]]:
        self._record("list_by_paragraph", owner=owner, paragraph_id=paragraph_id)
        return []

    def create(self, sentence_id: str, text: str, paragraph_id: str, owner: str = "") -> None:
        self._record("create", owner=owner, sentence_id=sentence_id, paragraph_id=paragraph_id)
        raise ParagraphNotFoundError(paragraph_id)

    def get(self, sentence_id: str, owner: str = "") -> None:
        self._record("get", owner=owner, sentence_id=sentence_id)

    def update(self, sentence_id: str, text: str, paragraph_id: str | None = None, owner: str = "") -> None:
        self._record("update", owner=owner, sentence_id=sentence_id)

    def delete(self, sentence_id: str, owner: str = "") -> bool:
        self._record("delete", owner=owner, sentence_id=sentence_id)
        return False


class StubHistoryService(_Recording):
    def list_snapshots(self, chapter_id: str, owner: str = "", *, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
        self._record("list_snapshots", owner=owner, chapter_id=chapter_id)
        return []

    def restore(self, chapter_id: str, commit_id: str, owner: str = "") -> None:
        self._record("restore", owner=owner, chapter_id=chapter_id)


class StubImportService(_Recording):
    async def import_parts(self, parts: Any, user_name: str, *, owner: str, single_newline_paragraphs: bool = False) -> list[Any]:
        self._record("import_parts", owner=owner, user_name=user_name)
        return [ChapterImportSummary(chapter_id="c1", created=True, title="Opening 1", category="Chapter")]


class StubAuthService:
    """The account store, which knows the caller's username for document metadata."""

    @staticmethod
    def get_user(user_id: str) -> dict[str, object] | None:
        if user_id != _OWNER:
            return None
        return {"id": _OWNER, "username": "abby"}


@dataclass
class Route:
    """One request, and the account the service stub recorded for it."""

    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    json: dict[str, Any] | None = None
    expect: int = 404
    expect_json: Any = None


_DOCUMENT = {"attrs": {"id": "d1", "title": "Faith", "author": "Paul"}}
_CHAPTER = {"attrs": {"id": "c1", "title": "Intro"}, "relations": {"document_id": "d1"}}
_SENTENCE_NODE = {"type": "sentence", "attrs": {"id": "s1"}, "content": [{"type": "text", "text": "Hello."}]}
_PARAGRAPH = {"attrs": {"id": "p1"}, "content": [_SENTENCE_NODE], "relations": {"chapter_id": "ch1"}}
_SENTENCE = {"attrs": {"id": "s1"}, "relations": {"paragraph_id": "p1"}, "content": [{"type": "text", "text": "Hello."}]}

ROUTES = [
    Route("GET", "/api/documents", expect=200, expect_json=[]),
    # A document has no parent to own, so a create always succeeds; it is stamped
    # with the caller's account, which is the assertion that matters here.
    Route("POST", "/api/documents", json=_DOCUMENT, expect=200),
    Route("GET", "/api/documents/d1"),
    Route("PUT", "/api/documents/d1", json=_DOCUMENT),
    Route("DELETE", "/api/documents/d1"),
    Route("GET", "/api/chapters", params={"document": "d1"}, expect=200, expect_json=[]),
    Route("POST", "/api/chapters", json=_CHAPTER, expect=404),
    Route("GET", "/api/chapters/c1"),
    Route("GET", "/api/chapters/c1/document"),
    Route("PUT", "/api/chapters/c1/document", json={"content": "text"}),
    Route("POST", "/api/chapters/c1/reorder", json={"after_chapter_id": None}),
    Route("PUT", "/api/chapters/c1", json={"attrs": {"title": "Renamed"}}),
    Route("DELETE", "/api/chapters/c1"),
    Route("GET", "/api/paragraphs", params={"chapter": "ch1"}, expect=200, expect_json=[]),
    Route("POST", "/api/paragraphs", json=_PARAGRAPH, expect=404),
    Route("GET", "/api/paragraphs/p1"),
    Route("PUT", "/api/paragraphs/p1", json={"attrs": {}, "content": [_SENTENCE_NODE]}),
    Route("DELETE", "/api/paragraphs/p1"),
    Route("GET", "/api/sentences", params={"paragraph": "p1"}, expect=200, expect_json=[]),
    Route("POST", "/api/sentences", json=_SENTENCE, expect=404),
    Route("GET", "/api/sentences/s1"),
    Route("PUT", "/api/sentences/s1", json={"attrs": {}, "content": [{"type": "text", "text": "New."}]}),
    Route("DELETE", "/api/sentences/s1"),
    Route("GET", "/api/history/c1", expect=200, expect_json={"snapshots": []}),
    Route("PATCH", "/api/history/c1", json={"commit_id": "abc"}),
]


def _app(services: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    for module in (documents, chapters, paragraphs, sentences, history, imports):
        app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: _OWNER
    app.dependency_overrides[get_auth_service] = StubAuthService
    documents.set_doc_service(services["documents"])
    chapters.set_ch_service(services["chapters"])
    paragraphs.set_para_service(services["paragraphs"])
    sentences.set_sent_service(services["sentences"])
    history.set_history_service(services["history"])
    imports.set_import_service(services["imports"])
    return app


@pytest.fixture()
def services():
    built = {
        "documents": StubDocumentService(),
        "chapters": StubChapterService(),
        "paragraphs": StubParagraphService(),
        "sentences": StubSentenceService(),
        "history": StubHistoryService(),
        "imports": StubImportService(),
    }
    yield built
    documents.set_doc_service(None)
    chapters.set_ch_service(None)
    paragraphs.set_para_service(None)
    sentences.set_sent_service(None)
    history.set_history_service(None)
    imports.set_import_service(None)


@pytest.fixture()
def client(services):
    return TestClient(_app(services))


def _service_for(services: dict[str, Any], path: str) -> _Recording:
    for prefix, key in (
        ("/api/documents", "documents"),
        ("/api/chapters", "chapters"),
        ("/api/paragraphs", "paragraphs"),
        ("/api/sentences", "sentences"),
        ("/api/history", "history"),
        ("/api/import", "imports"),
    ):
        if path.startswith(prefix):
            return services[key]
    raise AssertionError(f"no service for {path}")


def _send(client: TestClient, route: Route, files: dict[str, Any] | None = None) -> Any:
    if files is not None:
        return client.request(route.method, route.path, files=files)
    return client.request(route.method, route.path, params=route.params, json=route.json)


@pytest.mark.parametrize("route", ROUTES, ids=[f"{r.method} {r.path}" for r in ROUTES])
def test_route_answers_as_if_the_resource_were_absent(route: Route, client, services):
    response = _send(client, route, _files(route) if route.path == "/api/import" else None)

    assert response.status_code == route.expect, response.text
    if route.expect_json is not None:
        assert response.json() == route.expect_json


@pytest.mark.parametrize("route", ROUTES, ids=[f"{r.method} {r.path}" for r in ROUTES])
def test_route_acts_for_the_signed_in_account(route: Route, client, services):
    _send(client, route, _files(route) if route.path == "/api/import" else None)

    service = _service_for(services, route.path)
    assert service.calls, f"{route.path} never reached its service"
    assert {call["owner"] for call in service.calls} == {_OWNER}


def test_import_names_the_caller_by_username_and_owns_the_document_by_account(client, services):
    """A document's author is something a reader sees; its owner is not.

    The account id is what every later read is scoped by, so it is what the document is
    stamped with; the username is what the front matter records as the author.
    """
    client.post("/api/import", files=_files(Route("POST", "/api/import")))

    call = services["imports"].calls[0]
    assert call["owner"] == _OWNER
    assert call["user_name"] == "abby"


def _files(route: Route) -> dict[str, Any]:
    import io

    return {"files": ("Linchpin/Act I/1.md", io.BytesIO(b"body"), "text/markdown")}


def test_every_manuscript_route_is_covered():
    """The list above is the whole manuscript surface; a new route must be added here.

    An unwritten route is not caught by any other test, because nothing else claims to
    enumerate them — this does.
    """
    placeholder_ids = {"document_id": "d1", "chapter_id": "c1", "paragraph_id": "p1", "sentence_id": "s1"}
    registered = set()
    for module in (documents, chapters, paragraphs, sentences, history, imports):
        for route in module.router.routes:
            path = route.path
            for name, value in placeholder_ids.items():
                path = path.replace("{" + name + "}", value)
            for method in route.methods - {"HEAD", "OPTIONS"}:
                registered.add(f"{method} {path}")

    covered = {f"{r.method} {r.path}" for r in ROUTES} | {"POST /api/import"}
    assert registered == covered
