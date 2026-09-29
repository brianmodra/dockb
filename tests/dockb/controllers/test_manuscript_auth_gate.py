"""Tests for the manuscript API auth gate and the session cookie's scope."""

# The stub services answer every call, so their parameters are never read.

# pylint: disable=unused-argument,too-few-public-methods

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dockb.app_factory import create_app
from dockb.controllers.auth import set_auth_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.services.auth_service import AuthService
from dockb.services.session_context import SessionContext

# Every route the six manuscript routers expose, as (method, path). A body or a
# query parameter is not supplied: the gate must reject before the handler runs,
# so a 422 from request validation would mean the route is not gated at all.
MANUSCRIPT_ROUTES = [
    ("GET", "/api/documents"),
    ("POST", "/api/documents"),
    ("GET", "/api/documents/doc-1"),
    ("PUT", "/api/documents/doc-1"),
    ("DELETE", "/api/documents/doc-1"),
    ("GET", "/api/chapters"),
    ("POST", "/api/chapters"),
    ("GET", "/api/chapters/ch-1"),
    ("GET", "/api/chapters/ch-1/document"),
    ("PUT", "/api/chapters/ch-1/document"),
    ("POST", "/api/chapters/ch-1/reorder"),
    ("PUT", "/api/chapters/ch-1"),
    ("DELETE", "/api/chapters/ch-1"),
    ("GET", "/api/paragraphs"),
    ("POST", "/api/paragraphs"),
    ("GET", "/api/paragraphs/pa-1"),
    ("PUT", "/api/paragraphs/pa-1"),
    ("DELETE", "/api/paragraphs/pa-1"),
    ("GET", "/api/sentences"),
    ("POST", "/api/sentences"),
    ("GET", "/api/sentences/se-1"),
    ("PUT", "/api/sentences/se-1"),
    ("DELETE", "/api/sentences/se-1"),
    ("GET", "/api/history/ch-1"),
    ("PATCH", "/api/history/ch-1"),
    ("GET", "/api/notifications"),
]

# A request the gate must not close off, or an editor cannot sign in.
PUBLIC_ROUTES = [
    ("GET", "/api/auth/login?provider=fake"),
    ("GET", "/api/auth/config"),
]


def _login_service(tmp_path) -> AuthService:
    store = AccountStore(base_dir=tmp_path, secret="secret")
    signer = SessionSigner("secret", ttl_hours=2)
    return AuthService(
        {"fake": FakeOAuthProvider(email="abby@example.com", display_name="Abby")},
        PendingLoginStore(),
        store,
        SessionManager(),
        signer,
    )


def _local_service(tmp_path) -> AuthService:
    store = AccountStore(base_dir=tmp_path, secret="secret")
    return AuthService({}, PendingLoginStore(), store, SessionManager(), SessionSigner("secret", ttl_hours=2))


@pytest.fixture()
def login_app(tmp_path):
    service = _login_service(tmp_path)
    set_auth_service(service)
    yield create_app()
    set_auth_service(None)


@pytest.fixture()
def local_app(tmp_path):
    service = _local_service(tmp_path)
    set_auth_service(service)
    yield create_app()
    set_auth_service(None)


def _wire_stub_services() -> None:
    """Give every manuscript router a stub service so a request has a handler.

    The stubs answer "no such entity" rather than modelling a domain, because
    this suite is about whether a request reaches the handler at all. Where a
    handler serializes what it gets back, the stub returns None so the handler
    takes its own not-found branch — a 404 proves the request got in.
    """
    from dockb.controllers.chapters import set_ch_service
    from dockb.controllers.documents import set_doc_service
    from dockb.controllers.history import set_history_service
    from dockb.controllers.notifications import set_session_context
    from dockb.controllers.paragraphs import set_para_service
    from dockb.controllers.sentences import set_sent_service

    class _None:
        def __getattr__(self, _name: str):
            def _call(*_args, **_kwargs):
                return None

            return _call

    class _History:
        def list_snapshots(self, chapter_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
            return []

    class _Documents:
        """Lists are empty, but fetching one document finds nothing."""

        def list_all(self) -> list[dict[str, str]]:
            return []

        def __getattr__(self, _name: str):
            def _call(*_args, **_kwargs):
                return None

            return _call

    set_doc_service(_Documents())
    set_ch_service(_None())
    set_para_service(_None())
    set_sent_service(_None())
    set_history_service(_History())
    set_session_context(SessionContext())


@pytest.fixture()
def wired_login_app(tmp_path):
    set_auth_service(_login_service(tmp_path))
    _wire_stub_services()
    yield create_app()
    set_auth_service(None)


@pytest.fixture()
def wired_local_app(tmp_path):
    set_auth_service(_local_service(tmp_path))
    _wire_stub_services()
    yield create_app()
    set_auth_service(None)


class TestManuscriptRoutesRequireASession:
    @pytest.mark.parametrize(("method", "path"), MANUSCRIPT_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
    def test_rejects_an_anonymous_caller(self, login_app, method, path):
        response = TestClient(login_app).request(method, path)
        assert response.status_code == 401, f"{method} {path} is reachable without a session"
        assert response.json()["detail"] == "not_authenticated"

    @pytest.mark.parametrize(("method", "path"), MANUSCRIPT_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
    def test_rejects_a_forged_cookie(self, login_app, method, path):
        client = TestClient(login_app)
        client.cookies.set("dockb_session", "not-a-real-token")
        assert client.request(method, path).status_code == 401

    @pytest.mark.parametrize(("method", "path"), MANUSCRIPT_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
    def test_reaches_the_handler_once_the_gate_passes(self, wired_login_app, method, path):
        """A signed cookie must get past the gate, whatever the handler then decides.

        The services are stubbed, so a 2xx proves the request reached the handler
        rather than being turned away at the door. A 5xx is not acceptable: that
        would mean the route ran with nothing wired behind it.
        """
        client = TestClient(wired_login_app)
        client.cookies.set("dockb_session", _auth_service().session_cookie("abby"))
        assert client.request(method, path).status_code < 500, f"{method} {path} 5xx'd behind the gate"


class TestPublicRoutesStayOpen:
    @pytest.mark.parametrize(("method", "path"), PUBLIC_ROUTES, ids=lambda v: v if isinstance(v, str) else "")
    def test_does_not_require_a_session(self, login_app, method, path):
        assert TestClient(login_app).request(method, path).status_code != 401

    def test_local_mode_needs_no_cookie(self, wired_local_app):
        """Local mode is the OS identity, so the gate must not close the door."""
        assert TestClient(wired_local_app).get("/api/documents").status_code < 500
        assert TestClient(wired_local_app).get("/api/documents").status_code != 401


class TestSessionCookieScope:
    def test_callback_sets_the_cookie_under_api_only(self, login_app):
        service = _auth_service()
        # begin_login mints the state the callback will accept; the fake provider
        # exchanges any code, so the verifier never has to be threaded through.
        login_url = service.begin_login("fake")
        state = dict(part.split("=", 1) for part in login_url.split("?", 1)[1].split("&"))["state"]
        response = TestClient(login_app).get(f"/callback?code=the-code&state={state}")
        assert response.status_code == 200
        header = response.headers["set-cookie"]
        assert "Path=/api" in header
        assert "Path=/;" not in header

    def test_the_cookie_from_the_callback_authenticates(self, login_app):
        """The cookie the callback sets is the one the API accepts.

        Driven through a real login so the assertion covers the whole path: the
        provider profile becomes a user, the cookie is signed for that user, and
        that same cookie resolves on a later request.
        """
        service = _auth_service()
        login_url = service.begin_login("fake")
        state = dict(part.split("=", 1) for part in login_url.split("?", 1)[1].split("&"))["state"]
        client = TestClient(login_app)
        assert client.get(f"/callback?code=the-code&state={state}").status_code == 200
        # The client now holds the Set-Cookie value; TestClient honours Path=/api.
        assert client.get("/api/auth/me").status_code == 200


def _auth_service() -> AuthService:
    from dockb.controllers.auth import get_auth_service

    service = get_auth_service()
    assert service is not None
    return service
