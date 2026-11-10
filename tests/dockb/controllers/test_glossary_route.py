"""Tests for GET / PUT /api/documents/{document_id}/glossary."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.auth import get_current_user, get_owner
from dockb.controllers.glossary import get_glossary, put_glossary, set_glossary_service
from dockb.exceptions import DocumentNotFoundError


def _make_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_owner] = lambda: "acct-1"
    app.dependency_overrides[get_current_user] = lambda: "abby"
    app.add_api_route("/api/documents/{document_id}/glossary", get_glossary, methods=["GET"])
    app.add_api_route("/api/documents/{document_id}/glossary", put_glossary, methods=["PUT"])
    return app


class _StubService:  # pylint: disable=too-few-public-methods
    def __init__(self, words: list[str] | None = None, error: Exception | None = None) -> None:
        self.words = words or []
        self.error = error
        self.get_calls: list[tuple[str, str, str]] = []
        self.set_calls: list[tuple[str, list[str], str, str]] = []

    def get_words(self, document_id: str, *, owner: str, username: str) -> list[str]:
        self.get_calls.append((document_id, owner, username))
        if self.error is not None:
            raise self.error
        return list(self.words)

    def set_words(self, document_id: str, words: list[str], *, owner: str, username: str) -> list[str]:
        self.set_calls.append((document_id, list(words), owner, username))
        if self.error is not None:
            raise self.error
        return list(words)


class TestGlossaryRoute:
    def setup_method(self) -> None:
        self.client = TestClient(_make_app())

    def teardown_method(self) -> None:
        set_glossary_service(None)
        self.client.app.dependency_overrides.pop(get_owner, None)
        self.client.app.dependency_overrides.pop(get_current_user, None)

    def test_get_returns_the_stored_words(self) -> None:
        service = _StubService(words=["Karakas", "teh"])
        set_glossary_service(service)

        resp = self.client.get("/api/documents/doc-1/glossary")

        assert resp.status_code == 200
        assert resp.json() == {"words": ["Karakas", "teh"]}
        assert service.get_calls == [("doc-1", "acct-1", "abby")]

    def test_put_forwards_the_words_and_returns_the_saved_list(self) -> None:
        service = _StubService()
        set_glossary_service(service)

        resp = self.client.put("/api/documents/doc-1/glossary", json={"words": ["Karakas"]})

        assert resp.status_code == 200
        assert resp.json() == {"words": ["Karakas"]}
        assert service.set_calls == [("doc-1", ["Karakas"], "acct-1", "abby")]

    def test_without_a_service_answers_503(self) -> None:
        assert self.client.get("/api/documents/doc-1/glossary").status_code == 503
        assert self.client.put("/api/documents/doc-1/glossary", json={"words": []}).status_code == 503

    def test_an_absent_document_answers_404(self) -> None:
        set_glossary_service(_StubService(error=DocumentNotFoundError("doc-1")))

        assert self.client.get("/api/documents/doc-1/glossary").status_code == 404
        assert self.client.put("/api/documents/doc-1/glossary", json={"words": []}).status_code == 404

    def test_an_empty_body_is_a_valid_empty_glossary(self) -> None:
        service = _StubService()
        set_glossary_service(service)

        resp = self.client.put("/api/documents/doc-1/glossary", json={})

        assert resp.status_code == 200
        assert resp.json() == {"words": []}
