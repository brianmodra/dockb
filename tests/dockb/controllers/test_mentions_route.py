"""Tests for GET /api/documents/{document_id}/mentions."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.auth import get_current_user, get_owner
from dockb.controllers.mentions import document_mentions, set_mentions_repo


def _make_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_owner] = lambda: "acct-1"
    app.dependency_overrides[get_current_user] = lambda: "abby"
    app.add_api_route("/api/documents/{document_id}/mentions", document_mentions, methods=["GET"])
    return app


class _StubRepo:  # pylint: disable=too-few-public-methods
    def __init__(self, mentions: dict[str, list[str]]) -> None:
        self.mentions = mentions
        self.calls: list[tuple[str, str]] = []

    def document_mentions(self, document_id: str, owner: str) -> dict[str, list[str]]:
        self.calls.append((document_id, owner))
        return self.mentions


class TestMentionsRoute:
    def setup_method(self) -> None:
        self.client = TestClient(_make_app())

    def teardown_method(self) -> None:
        set_mentions_repo(None)
        self.client.app.dependency_overrides.pop(get_owner, None)
        self.client.app.dependency_overrides.pop(get_current_user, None)

    def test_returns_the_documents_mention_map(self) -> None:
        repo = _StubRepo({"p1": ["k1", "k2"]})
        set_mentions_repo(repo)

        resp = self.client.get("/api/documents/doc-1/mentions")

        assert resp.status_code == 200
        assert resp.json() == {"mentions": {"p1": ["k1", "k2"]}}
        assert repo.calls == [("doc-1", "acct-1")]

    def test_without_a_repo_answers_503(self) -> None:
        assert self.client.get("/api/documents/doc-1/mentions").status_code == 503
