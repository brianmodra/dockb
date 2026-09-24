"""Tests for the auth routes: login URL endpoint and loopback callback page."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from dockb.controllers.auth import auth_callback, auth_login, auth_me, get_current_session_context, set_auth_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.services.auth_service import AuthService


def _make_app() -> FastAPI:
    app = FastAPI()

    def context_check(user_id: str = Depends(get_current_session_context)) -> dict[str, str]:  # pylint: disable=unused-argument
        return {"ok": "yes"}

    app.add_api_route("/api/auth/login", auth_login, methods=["GET"])
    app.add_api_route("/callback", auth_callback, methods=["GET"])
    app.add_api_route("/api/auth/me", auth_me, methods=["GET"])
    app.add_api_route("/api/auth/context-check", context_check, methods=["GET"])
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


class TestLoginEndpoint:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_auth_service(None)

    def test_login_returns_consent_url(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/auth/login", params={"provider": "fake"})
        assert resp.status_code == 200
        url = resp.json()["authorization_url"]
        assert url.startswith("https://fake.example/authorize?")
        assert "state=" in url

    def test_login_unknown_provider_returns_400(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/auth/login", params={"provider": "myspace"})
        assert resp.status_code == 400

    def test_login_without_service_returns_400(self) -> None:
        set_auth_service(None)
        resp = self.client.get("/api/auth/login", params={"provider": "fake"})
        assert resp.status_code == 503


class TestCallbackEndpoint:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_auth_service(None)

    def _login_url_state(self, tmp_path) -> str:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/auth/login", params={"provider": "fake"})
        url = resp.json()["authorization_url"]
        return url.split("state=")[1].split("&")[0]

    def test_callback_sets_httponly_session_cookie(self, tmp_path) -> None:
        state = self._login_url_state(tmp_path)
        resp = self.client.get("/callback", params={"code": "the-code", "state": state})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "signed in" in resp.text.lower()
        set_cookie = resp.headers["set-cookie"]
        assert "dockb_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Path=/;" in set_cookie
        assert "Max-Age=7200;" in set_cookie

    def test_callback_with_bad_state_shows_error_no_cookie(self, tmp_path) -> None:
        self._login_url_state(tmp_path)
        resp = self.client.get("/callback", params={"code": "the-code", "state": "forged"})
        assert resp.status_code == 200
        assert "sign-in failed" in resp.text.lower()
        assert "set-cookie" not in resp.headers

    def test_callback_escapes_provider_error_text(self, tmp_path) -> None:
        state = self._login_url_state(tmp_path)
        resp = self.client.get("/callback", params={"code": "", "state": state, "error": "<script>alert(1)</script>"})
        assert resp.status_code == 200
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_callback_with_provider_error_shows_error_no_cookie(self, tmp_path) -> None:
        state = self._login_url_state(tmp_path)
        resp = self.client.get("/callback", params={"code": "", "state": state, "error": "access_denied"})
        assert resp.status_code == 200
        assert "sign-in failed" in resp.text.lower()
        assert "access_denied" in resp.text
        assert "set-cookie" not in resp.headers


class TestMeEndpoint:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_auth_service(None)

    def _authenticated_cookie(self, tmp_path) -> str:
        set_auth_service(_build_service(tmp_path))
        login = self.client.get("/api/auth/login", params={"provider": "fake"})
        state = login.json()["authorization_url"].split("state=")[1].split("&")[0]
        callback = self.client.get("/callback", params={"code": "the-code", "state": state})
        return callback.cookies.get("dockb_session")

    def test_me_without_cookie_returns_401(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_returns_profile(self, tmp_path) -> None:
        cookie = self._authenticated_cookie(tmp_path)
        self.client.cookies.set("dockb_session", cookie)
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["email"] == "abby@example.com"
        assert user["display_name"] == "Abby"
        assert user["avatar_url"]

    def test_me_returns_username_of_authenticated_user(self, tmp_path) -> None:
        cookie = self._authenticated_cookie(tmp_path)
        self.client.cookies.set("dockb_session", cookie)
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "fake-user"

    def test_me_with_tampered_cookie_returns_401(self, tmp_path) -> None:
        self._authenticated_cookie(tmp_path)
        self.client.cookies.set("dockb_session", "forged-session")
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_valid_signature_unknown_user_returns_401(self, tmp_path) -> None:
        service = _build_service(tmp_path)
        set_auth_service(service)
        self.client.cookies.set("dockb_session", service.session_cookie("no-such-user"))
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_in_local_mode_without_cookie_returns_local_profile(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("USER", "dave")
        set_auth_service(_build_local_service(tmp_path))
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["username"] == "dave"
        assert user["display_name"] == "dave"
        assert user["email"] == ""

    def test_me_in_local_mode_is_idempotent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("USER", "dave")
        set_auth_service(_build_local_service(tmp_path))
        assert self.client.get("/api/auth/me").status_code == 200
        assert self.client.get("/api/auth/me").status_code == 200

    def test_me_in_local_mode_falls_back_to_getpass(self, tmp_path, monkeypatch) -> None:
        import getpass

        monkeypatch.delenv("USER", raising=False)
        monkeypatch.setattr(getpass, "getuser", lambda: "local-user")
        set_auth_service(_build_local_service(tmp_path))
        resp = self.client.get("/api/auth/me")
        user = resp.json()["user"]
        assert user["username"] == "local-user"
        assert user["avatar_url"] == ""

    def test_me_in_oauth_mode_without_cookie_returns_401(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        resp = self.client.get("/api/auth/me")
        assert resp.status_code == 401


class TestLocalModeMe:
    def setup_method(self) -> None:
        self.app = _make_app()
        self.client = TestClient(self.app)

    def teardown_method(self) -> None:
        set_auth_service(None)

    def test_login_endpoint_returns_400_in_local_mode(self, tmp_path) -> None:
        set_auth_service(_build_local_service(tmp_path))
        resp = self.client.get("/api/auth/login", params={"provider": "google"})
        assert resp.status_code == 400

    def test_context_check_with_live_session_ok(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        login = self.client.get("/api/auth/login", params={"provider": "fake"})
        state = login.json()["authorization_url"].split("state=")[1].split("&")[0]
        callback = self.client.get("/callback", params={"code": "the-code", "state": state})
        self.client.cookies.set("dockb_session", callback.cookies.get("dockb_session"))
        resp = self.client.get("/api/auth/context-check")
        assert resp.status_code == 200

    def test_context_check_after_restart_returns_401(self, tmp_path) -> None:
        set_auth_service(_build_service(tmp_path))
        login = self.client.get("/api/auth/login", params={"provider": "fake"})
        state = login.json()["authorization_url"].split("state=")[1].split("&")[0]
        callback = self.client.get("/callback", params={"code": "the-code", "state": state})
        cookie = callback.cookies.get("dockb_session")
        set_auth_service(_build_service(tmp_path))
        self.client.cookies.set("dockb_session", cookie)
        resp = self.client.get("/api/auth/context-check")
        assert resp.status_code == 401
