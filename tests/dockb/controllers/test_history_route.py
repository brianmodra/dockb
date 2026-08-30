"""Tests for History route handlers (GET/PATCH /api/history/{chapter_id}).

Uses mocked HistoryService and TestClient — no Neo4j or git required.
"""

# pylint: disable=unused-argument

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.exceptions import SnapshotError
from dockb.models.base import DataState
from dockb.models.chapter import Chapter


def _make_chapter(ch_id: str = "c1", title: str = "Ch1") -> Chapter:
    ch = Chapter(id=ch_id, title=title, state=DataState.SYNC)
    return ch


class MockHistoryService:
    def __init__(self) -> None:
        self._snapshots: list[dict[str, str]] = []
        self._chapters: dict[str, Chapter] = {}

    def list_snapshots(self, chapter_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
        return self._snapshots[offset : offset + limit]

    def restore(self, chapter_id: str, commit_id: str) -> Chapter:
        if chapter_id not in self._chapters:
            raise SnapshotError(f"Snapshot not found for {chapter_id}")
        return self._chapters[chapter_id]


def _build_app(svc: MockHistoryService | None = None) -> FastAPI:
    from dockb.controllers.history import router as history_router
    from dockb.controllers.history import set_history_service

    set_history_service(svc or MockHistoryService())

    app = FastAPI()
    app.include_router(history_router)
    return app


# ---------------------------------------------------------------------------
# GET /api/history/{chapter_id}
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_empty_history(self) -> None:
        app = _build_app()
        client = TestClient(app)
        resp = client.get("/api/history/c1")
        assert resp.status_code == 200
        assert resp.json() == {"snapshots": []}

    def test_with_snapshots(self) -> None:
        svc = MockHistoryService()
        svc._snapshots = [
            {"commit_id": "abc123", "datetime": "2026-01-01T00:00:00+00:00"},
            {"commit_id": "def456", "datetime": "2025-12-31T00:00:00+00:00"},
        ]
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.get("/api/history/c1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["snapshots"]) == 2
        assert data["snapshots"][0]["commit_id"] == "abc123"

    def test_pagination_params(self) -> None:
        svc = MockHistoryService()
        svc._snapshots = [
            {"commit_id": "a", "datetime": "2026-01-03"},
            {"commit_id": "b", "datetime": "2026-01-02"},
            {"commit_id": "c", "datetime": "2026-01-01"},
        ]
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.get("/api/history/c1?limit=1&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["snapshots"]) == 1
        assert data["snapshots"][0]["commit_id"] == "b"


# ---------------------------------------------------------------------------
# PATCH /api/history/{chapter_id}
# ---------------------------------------------------------------------------


class TestPatchHistory:
    def test_restore_returns_chapter(self) -> None:
        svc = MockHistoryService()
        ch = _make_chapter(ch_id="c1", title="Restored")
        svc._chapters["c1"] = ch
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.patch("/api/history/c1", json={"commit_id": "abc123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["attrs"]["id"] == "c1"
        assert data["attrs"]["title"] == "Restored"

    def test_restore_not_found(self) -> None:
        svc = MockHistoryService()
        app = _build_app(svc)
        client = TestClient(app)
        resp = client.patch("/api/history/c-nonexistent", json={"commit_id": "abc"})
        assert resp.status_code == 500
