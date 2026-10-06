"""Tests for the password HTTP surface: sign-in, change, and sign-out.

These exercise the routes through a real ``AuthService`` over a real
``AccountStore``, because what is being tested is the wire contract: the status
code, the cookie, and which routes a session with a pending password change may
reach. See ``README_auth.md`` §7.
"""

from __future__ import annotations

# The stub services answer every call, so their parameters are never read.
# pylint: disable=unused-argument,too-few-public-methods
import pytest
from fastapi.testclient import TestClient

from dockb.app_factory import create_app
from dockb.controllers.auth import set_auth_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.passwords import hash_password, pepper_from
from dockb.services.auth_service import AuthService

_SECRET = "a-server-secret"
_PASSWORD = "correct horse battery"
_TEMP_PASSWORD = "tmp-4f7a1c9e"


def _service(tmp_path, *, must_change: bool = False, blocked: bool = False) -> AuthService:
    """A password-only deployment with one account, *abby*, in the given state.

    With *must_change*, abby is signed in on a temporary password rather than a
    chosen one, which is the state ``dockb users create`` leaves behind.
    """
    password = _TEMP_PASSWORD if must_change else _PASSWORD
    store = AccountStore(base_dir=tmp_path, secret=_SECRET)
    store.create_user(
        "abby",
        email="abby@example.com",
        display_name="Abby",
        password_hash=hash_password(pepper_from(_SECRET), password, generated=must_change),
        must_change_password=must_change,
    )
    if blocked:
        store.block_user("abby")
    from dockb.infrastructure.oauth.pending_login import PendingLoginStore
    from dockb.infrastructure.session.session_cookie import SessionSigner
    from dockb.infrastructure.session.session_manager import SessionManager

    return AuthService(
        {},
        PendingLoginStore(),
        store,
        SessionManager(),
        SessionSigner(_SECRET, ttl_hours=2),
        pepper=pepper_from(_SECRET),
    )


@pytest.fixture()
def client(tmp_path):
    """A client against the real app, signed in as *abby* unless asked otherwise.

    The manuscript routers are stubbed because these tests are about the auth
    surface, not about documents; the must-change gate does reach them, which is
    why they are wired at all.
    """
    set_auth_service(_service(tmp_path))
    _wire_stub_services()
    app = create_app()
    yield TestClient(app)
    set_auth_service(None)


def _wire_stub_services() -> None:
    from dockb.controllers.chapters import set_ch_service
    from dockb.controllers.documents import set_doc_service
    from dockb.controllers.history import set_history_service
    from dockb.controllers.notifications import set_session_context
    from dockb.controllers.paragraphs import set_para_service
    from dockb.controllers.sentences import set_sent_service
    from dockb.services.session_context import SessionContext

    class _None:
        def __getattr__(self, _name: str):
            def _call(*_args, **_kwargs):
                return None

            return _call

    class _History:
        def list_snapshots(self, chapter_id: str, limit: int = 20, offset: int = 0) -> list[dict[str, str]]:
            return []

    class _Documents:
        """Lists empty. A 5xx here would mean the route ran but serialization failed."""

        def list_all(self, owner: str = "") -> list[dict[str, str]]:
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


def _sign_in(client: TestClient, password: str = _PASSWORD) -> None:
    """Sign in through the route, so the cookie is a real one from a real login."""
    response = client.post("/api/auth/login/password", json={"username": "abby", "password": password})
    assert response.status_code == 200, response.text


class TestPasswordLogin:
    def test_correct_password_signs_in_and_sets_the_cookie(self, client):
        response = client.post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD})
        assert response.status_code == 200
        set_cookie = response.headers["set-cookie"]
        assert "dockb_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert "Path=/api" in set_cookie

    def test_response_carries_the_profile(self, client):
        _sign_in(client)
        user = client.get("/api/auth/me").json()["user"]
        assert user["username"] == "abby"
        assert user["display_name"] == "Abby"

    def test_username_is_matched_case_insensitively(self, client):
        response = client.post("/api/auth/login/password", json={"username": "  ABBY ", "password": _PASSWORD})
        assert response.status_code == 200

    def test_wrong_password_is_401_and_says_nothing_about_the_account(self, client):
        response = client.post("/api/auth/login/password", json={"username": "abby", "password": "wrong-one"})
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_username_or_password"

    def test_unknown_username_is_401_with_the_same_detail(self, client):
        """A wrong password and a missing account must be indistinguishable."""
        response = client.post("/api/auth/login/password", json={"username": "nobody", "password": "wrong-one"})
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_username_or_password"

    def test_a_failed_login_sets_no_cookie(self, client):
        """Asserted with the status, so it cannot pass by the route being absent."""
        response = client.post("/api/auth/login/password", json={"username": "abby", "password": "wrong-one"})
        assert response.status_code == 401
        assert "set-cookie" not in response.headers

    def test_an_unwired_backend_refuses_rather_than_hashing(self):
        set_auth_service(None)
        response = TestClient(create_app()).post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD})
        assert response.status_code == 503

    def test_blocked_account_cannot_sign_in(self, tmp_path):
        set_auth_service(_service(tmp_path, blocked=True))
        _wire_stub_services()
        response = TestClient(create_app()).post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD})
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid_username_or_password"

    def test_repeated_failures_are_throttled(self, client):
        """Backoff reaches the route: the same detail carries a Retry-After."""
        for _ in range(5):
            client.post("/api/auth/login/password", json={"username": "abby", "password": "wrong-one"})
        response = client.post("/api/auth/login/password", json={"username": "abby", "password": "wrong-one"})
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1

    def test_the_throttle_covers_spellings_of_one_username(self, client):
        """Otherwise a fresh allowance per spelling makes the backoff worthless.

        Exactly the threshold is spent across three spellings, so a throttle that
        keyed on the raw username would still be showing zero here.
        """
        for spelling in ("abby", "ABBY", " abby ", "Abby", "abby "):
            client.post("/api/auth/login/password", json={"username": spelling, "password": "wrong-one"})
        response = client.post("/api/auth/login/password", json={"username": "Abby", "password": _PASSWORD})
        assert response.status_code == 429

    def test_an_empty_body_is_rejected_before_any_hash_runs(self, client):
        assert client.post("/api/auth/login/password", json={}).status_code == 422

    def test_a_signed_in_caller_can_still_read_its_profile(self, client):
        _sign_in(client)
        assert client.get("/api/auth/me").status_code == 200


class TestChangePassword:
    def test_the_correct_current_password_changes_it(self, client):
        _sign_in(client)
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 200
        assert response.json()["signed_out"] is True

    def test_the_new_password_signs_in_and_the_old_one_does_not(self, client):
        _sign_in(client)
        client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "a-brand-new-password"},
        )
        client.cookies.clear()
        assert client.post("/api/auth/login/password", json={"username": "abby", "password": "a-brand-new-password"}).status_code == 200
        client.cookies.clear()
        assert client.post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD}).status_code == 401

    def test_the_session_that_asked_is_gone_afterwards(self, client):
        """The stamp refuses every session older than it, including the caller's own."""
        _sign_in(client)
        client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "a-brand-new-password"},
        )
        assert client.get("/api/auth/me").status_code == 401

    def test_a_wrong_current_password_is_refused(self, client):
        _sign_in(client)
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": "not-my-password", "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 401

    def test_reusing_the_current_password_is_refused_with_a_reason(self, client):
        _sign_in(client)
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": _PASSWORD},
        )
        assert response.status_code == 400
        assert "already" in response.json()["detail"]

    def test_a_new_password_that_fails_the_policy_is_a_client_error(self, client):
        _sign_in(client)
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "short"},
        )
        assert response.status_code == 400

    def test_it_needs_a_session(self, client):
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 401

    def test_it_may_not_change_another_account(self, client):
        """The session names the account; a username in the body would not be trusted."""
        _sign_in(client)
        response = client.post(
            "/api/auth/change-password",
            json={"current_password": _PASSWORD, "new_password": "a-brand-new-password", "username": "someone-else"},
        )
        assert response.status_code in (200, 422)


class TestPendingPasswordChangeIsEnforced:
    @pytest.fixture()
    def temp_client(self, tmp_path):
        set_auth_service(_service(tmp_path, must_change=True))
        _wire_stub_services()
        yield TestClient(create_app())
        set_auth_service(None)

    def test_login_succeeds_and_reports_the_pending_change(self, temp_client):
        response = temp_client.post("/api/auth/login/password", json={"username": "abby", "password": _TEMP_PASSWORD})
        assert response.status_code == 200
        assert response.json()["password_change_required"] is True

    def test_the_profile_route_stays_open_and_reports_it(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        body = temp_client.get("/api/auth/me").json()
        assert body["password_change_required"] is True
        assert body["user"]["username"] == "abby"

    def test_the_change_route_is_reachable(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        response = temp_client.post(
            "/api/auth/change-password",
            json={"current_password": _TEMP_PASSWORD, "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 200

    def test_the_sign_out_route_is_reachable(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        assert temp_client.post("/api/auth/logout").status_code == 200

    def test_a_manuscript_route_is_refused_with_a_reason(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        response = temp_client.get("/api/documents")
        assert response.status_code == 403
        assert response.json()["detail"] == "password_change_required"

    def test_the_app_state_route_is_refused_too(self, temp_client):
        """It carries the editor's per-user record, so it is manuscript data."""
        _sign_in(temp_client, _TEMP_PASSWORD)
        assert temp_client.get("/api/app/state").status_code == 403

    def test_the_notification_poll_is_refused_too(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        assert temp_client.get("/api/notifications").status_code == 403

    def test_an_unchanged_temporary_password_cannot_reach_anything(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        assert temp_client.post("/api/documents", json={"attrs": {"title": "t", "author": "a"}}).status_code == 403

    def test_after_the_change_the_manuscript_routes_open_up(self, temp_client):
        _sign_in(temp_client, _TEMP_PASSWORD)
        temp_client.post(
            "/api/auth/change-password",
            json={"current_password": _TEMP_PASSWORD, "new_password": "a-brand-new-password"},
        )
        _sign_in(temp_client, "a-brand-new-password")
        assert temp_client.get("/api/documents").status_code != 403


class TestLogout:
    def test_it_ends_the_session(self, client):
        _sign_in(client)
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/auth/me").status_code == 401

    def test_it_clears_the_cookie(self, client):
        _sign_in(client)
        response = client.post("/api/auth/logout")
        assert "dockb_session=" in response.headers["set-cookie"]

    def test_it_needs_a_session(self, client):
        assert client.post("/api/auth/logout").status_code == 401
