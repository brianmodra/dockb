"""Tests for AuthService — begin login, complete the callback, issue session cookie."""

from __future__ import annotations

import pytest

from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.services.auth_service import AuthService, InvalidLoginStateError, UnknownProviderError

_VERIFIER_LENGTH = 43


def _build(tmp_path):
    store = AccountStore(base_dir=tmp_path, secret="secret")
    pending = PendingLoginStore()
    sessions = SessionManager()
    signer = SessionSigner("secret", ttl_hours=2)
    fake = FakeOAuthProvider(
        provider_account_id="provider-acct-1",
        email="abby@example.com",
        display_name="Abby",
        avatar_url="https://img/abby.png",
    )
    service = AuthService({"fake": fake}, pending, store, sessions, signer)
    return service, store, sessions, fake


def test_begin_login_returns_consent_url(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    url = service.begin_login("fake")
    assert url.startswith("https://fake.example/authorize?")
    assert "state=" in url


def test_begin_login_unknown_provider_raises(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    with pytest.raises(UnknownProviderError):
        service.begin_login("myspace")


def test_complete_login_creates_account_and_session(tmp_path) -> None:
    service, store, sessions, _ = _build(tmp_path)
    url = service.begin_login("fake")
    state = url.split("state=")[1].split("&")[0]
    user_id = service.complete_login(state=state, code="the-code")
    assert user_id
    assert store.get_app_state(user_id) is None
    assert sessions.get(user_id) is not None
    account = store.get_provider_account("fake", "provider-acct-1")
    assert account is not None
    assert account["token"] == "fake-refresh-token"


def test_complete_login_returns_same_user_on_second_login(tmp_path) -> None:
    service, store, _, _ = _build(tmp_path)
    first_state = service.begin_login("fake").split("state=")[1].split("&")[0]
    first_user = service.complete_login(first_state, "code-1")
    second_state = service.begin_login("fake").split("state=")[1].split("&")[0]
    second_user = service.complete_login(second_state, "code-2")
    assert first_user == second_user
    assert store.get_user(first_user) is not None


def test_complete_login_with_bad_state_raises(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    with pytest.raises(InvalidLoginStateError):
        service.complete_login(state="never-issued", code="x")


def test_complete_login_consumes_state_once(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    state = service.begin_login("fake").split("state=")[1].split("&")[0]
    service.complete_login(state, "code-1")
    with pytest.raises(InvalidLoginStateError):
        service.complete_login(state, "code-2")


def test_session_cookie_round_trip(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    cookie = service.session_cookie("user-1")
    assert cookie
    assert cookie != "user-1"
    assert service.session_ttl_seconds == 2 * 3600


def test_authenticate_cookie_round_trip(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    cookie = service.session_cookie("user-1")
    assert service.authenticate_cookie(cookie) == "user-1"
    assert service.authenticate_cookie("garbage") is None


def test_get_user_returns_profile(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    state = service.begin_login("fake").split("state=")[1].split("&")[0]
    user_id = service.complete_login(state, "code")
    profile = service.get_user(user_id)
    assert profile is not None
    assert profile["email"] == "abby@example.com"
    assert profile["display_name"] == "Abby"


def test_get_user_unknown_returns_none(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    assert service.get_user("no-such-user") is None


def test_session_for_after_login_is_live(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    state = service.begin_login("fake").split("state=")[1].split("&")[0]
    user_id = service.complete_login(state, "code")
    assert service.session_for(user_id) is not None


def test_session_for_unknown_user_is_none(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    assert service.session_for("no-such-user") is None
