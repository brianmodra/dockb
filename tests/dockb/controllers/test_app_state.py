"""Tests for per-user app-state endpoints: GET and PUT /api/app/state."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.app_state import get_app_state, put_app_state
from dockb.controllers.auth import auth_callback, auth_login, set_auth_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.services.auth_service import AuthService


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_api_route("/api/auth/login", auth_login, methods=["GET"])
    app.add_api_route("/callback", auth_callback, methods=["GET"])
    app.add_api_route("/api/app/state", get_app_state, methods=["GET"])
    app.add_api_route("/api/app/state", put_app_state, methods=["PUT"])
    return app


def _build_service(tmp_path) -> AuthService:
    store = AccountStore(base_dir=tmp_path, secret="secret")
    pending = PendingLoginStore()
    sessions = SessionManager()
    signer = SessionSigner("secret", ttl_hours=2)
    fake = FakeOAuthProvider(email="abby@example.com", display_name="Abby")
    return AuthService({"fake": fake}, pending, store, sessions, signer)


def _build_local_service(tmp_path) -> AuthService:
    store = AccountStore(base_dir=tmp_path, secret="secret")
    pending = PendingLoginStore()
    sessions = SessionManager()
    signer = SessionSigner("secret", ttl_hours=2)
    return AuthService({}, pending, store, sessions, signer)


class TestAppState:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_auth_service(None)

    def _sign_in(self, tmp_path) -> str:
        set_auth_service(_build_service(tmp_path))
        login = self.client.get("/api/auth/login", params={"provider": "fake"})
        state = login.json()["authorization_url"].split("state=")[1].split("&")[0]
        callback = self.client.get("/callback", params={"code": "the-code", "state": state})
        assert callback.status_code == 200
        return callback.cookies.get("dockb_session")

    def test_get_without_session_returns_401(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/app/state")
        assert resp.status_code == 401

    def test_get_with_no_state_returns_defaults(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        resp = self.client.get("/api/app/state")
        assert resp.status_code == 200
        assert resp.json() == {"last_document_id": None, "panel_widths": None, "edit_mode": None}

    def test_put_then_get_round_trips(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        put = self.client.put("/api/app/state", json={"last_document_id": "doc-1", "panel_widths": {"left": 300}, "edit_mode": "wysiwyg"})
        assert put.status_code == 200
        assert put.json()["last_document_id"] == "doc-1"
        assert put.json()["panel_widths"] == {"left": 300}
        got = self.client.get("/api/app/state")
        assert got.json()["last_document_id"] == "doc-1"
        assert got.json()["panel_widths"] == {"left": 300}
        assert got.json()["edit_mode"] == "wysiwyg"

    def test_put_replaces_zeroing_absent_fields(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        self.client.put("/api/app/state", json={"last_document_id": "doc-1", "edit_mode": "raw"})
        self.client.put("/api/app/state", json={"edit_mode": "wysiwyg"})
        got = self.client.get("/api/app/state")
        assert got.json()["last_document_id"] is None
        assert got.json()["edit_mode"] == "wysiwyg"

    def test_empty_put_is_accepted(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        put = self.client.put("/api/app/state", json={})
        assert put.status_code == 200
        assert put.json()["last_document_id"] is None

    def test_state_is_per_user(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        self.client.put("/api/app/state", json={"last_document_id": "doc-1"})
        store = AccountStore(base_dir=tmp_path, secret="secret")
        pending = PendingLoginStore()
        sessions = SessionManager()
        signer = SessionSigner("secret", ttl_hours=2)
        fake = FakeOAuthProvider(provider_account_id="fake-bob", username="bob", email="bob@example.com", display_name="Bob")
        set_auth_service(AuthService({"fake": fake}, pending, store, sessions, signer))
        login = self.client.get("/api/auth/login", params={"provider": "fake"})
        state = login.json()["authorization_url"].split("state=")[1].split("&")[0]
        callback = self.client.get("/callback", params={"code": "the-code", "state": state})
        assert callback.status_code == 200
        got = self.client.get("/api/app/state")
        assert got.json()["last_document_id"] is None

    def test_local_mode_state_uses_os_username(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("USER", "dave")
        set_auth_service(_build_local_service(tmp_path))
        put = self.client.put("/api/app/state", json={"last_document_id": "doc-9"})
        assert put.status_code == 200
        got = self.client.get("/api/app/state")
        assert got.status_code == 200
        assert got.json()["last_document_id"] == "doc-9"

    def test_local_mode_state_no_cookie_required(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("USER", "dave")
        set_auth_service(_build_local_service(tmp_path))
        assert self.client.get("/api/app/state").status_code == 200

    def test_local_mode_state_is_per_os_user(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("USER", "dave")
        set_auth_service(_build_local_service(tmp_path))
        self.client.put("/api/app/state", json={"last_document_id": "dave-doc"})
        monkeypatch.setenv("USER", "kate")
        set_auth_service(_build_local_service(tmp_path))
        got = self.client.get("/api/app/state")
        assert got.json()["last_document_id"] is None

    def test_invalid_panel_widths_type_returns_422(self, tmp_path) -> None:
        self._sign_in(tmp_path)
        resp = self.client.put("/api/app/state", json={"panel_widths": "not-an-object"})
        assert resp.status_code == 422
