"""Tests for GET /api/notifications poll endpoint.

Returns all pending notifications from the SessionContext and clears
the queue.  Returns an empty array when there are none.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.notifications import get_notifications, set_session_context
from dockb.services.session_context import Notification, SessionContext


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_api_route("/api/notifications", get_notifications, methods=["GET"])
    return app


class TestNotificationsRoute:
    """GET /api/notifications returns and clears pending notifications."""

    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_session_context(None)

    def test_no_session_returns_empty_array(self) -> None:
        set_session_context(None)
        resp = self.client.get("/api/notifications")
        assert resp.status_code == 200
        assert resp.json()["notifications"] == []

    def test_empty_queue_returns_empty_array(self) -> None:
        set_session_context(SessionContext())
        resp = self.client.get("/api/notifications")
        assert resp.status_code == 200
        assert resp.json()["notifications"] == []

    def test_returns_pending_notifications(self) -> None:
        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1", "changed_sentences": []}))
        set_session_context(ctx)
        resp = self.client.get("/api/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["notifications"]) == 1
        n = data["notifications"][0]
        assert n["type"] == "sentence_split"
        assert n["paragraph_id"] == "p1"

    def test_cleared_after_first_poll(self) -> None:
        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        set_session_context(ctx)
        self.client.get("/api/notifications")
        resp2 = self.client.get("/api/notifications")
        assert resp2.json()["notifications"] == []

    def test_multiple_notifications(self) -> None:
        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        ctx.add_notification(Notification(type="paragraph_split", payload={"chapter_id": "ch1"}))
        set_session_context(ctx)
        resp = self.client.get("/api/notifications")
        data = resp.json()
        assert len(data["notifications"]) == 2
        types = {n["type"] for n in data["notifications"]}
        assert types == {"sentence_split", "paragraph_split"}
