"""Tests for AuthService — password sign-in, change, session resolve, and the OAuth flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.passwords import PasswordPolicyError, hash_password, pepper_from
from dockb.services.auth_service import (
    AuthService,
    InvalidLoginStateError,
    LoginFailedError,
    PasswordUnchangedError,
    RateLimitedError,
    UnknownProviderError,
)

_VERIFIER_LENGTH = 43
_SECRET = "a-server-secret"
_PEPPER = pepper_from(_SECRET)
_PASSWORD = "correct horse battery"


class _Clock:
    """A hand-advanced clock, so backoff and credential stamping need no sleeping.

    It starts at the real current time rather than a fixed date, because the store stamps
    ``credentials_changed_at`` from the real clock and the two are compared. A fixed date
    would make the credential-invalidation tests pass only while that date stayed in the
    past.
    """

    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _build(tmp_path):
    """An AuthService with one OAuth provider, and a clock both services share."""
    clock = _Clock()
    store = AccountStore(base_dir=tmp_path, secret=_SECRET)
    pending = PendingLoginStore()
    sessions = SessionManager(clock)
    signer = SessionSigner(_SECRET, ttl_hours=2)
    fake = FakeOAuthProvider(
        provider_account_id="provider-acct-1",
        email="abby@example.com",
        display_name="Abby",
        avatar_url="https://img/abby.png",
    )
    service = AuthService({"fake": fake}, pending, store, sessions, signer, pepper=_PEPPER, clock=clock)
    return service, store, sessions, fake


def _build_password_only(tmp_path):
    """An AuthService with no OAuth provider: password is the only way in."""
    clock = _Clock()
    store = AccountStore(base_dir=tmp_path, secret=_SECRET)
    sessions = SessionManager(clock)
    service = AuthService(
        {},
        PendingLoginStore(),
        store,
        sessions,
        SessionSigner(_SECRET, ttl_hours=2),
        pepper=_PEPPER,
        clock=clock,
    )
    return service, store, sessions, clock


def _temporary(password: str) -> str:
    """Hash a temporary password, which is generated and so exempt from the minimum."""
    return hash_password(_PEPPER, password, generated=True)


def _with_password(tmp_path, username="abby", password=_PASSWORD, **kwargs):
    """Build a password-only service holding one account able to sign in.

    An account flagged ``must_change_password`` is holding a *generated* password, so it
    is hashed exempt from the minimum — the same pairing the CLI produces.
    """
    service, store, sessions, clock = _build_password_only(tmp_path)
    must_change = kwargs.get("must_change_password", False)
    store.create_user(
        username=username,
        email=kwargs.get("email"),
        display_name="Abby",
        password_hash=hash_password(_PEPPER, password, generated=must_change),
        must_change_password=must_change,
    )
    return service, store, sessions, clock


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


def test_complete_login_returns_username(tmp_path) -> None:
    service, store, sessions, fake = _build(tmp_path)
    state = service.begin_login("fake").split("state=")[1].split("&")[0]
    username = service.complete_login(state, "code")
    assert username == fake.fetch_profile("t").username
    assert store.get_user(username) is not None
    assert sessions.get(username) is not None


def test_requires_login_is_true_when_providers_configured(tmp_path) -> None:
    service, _, _, _ = _build(tmp_path)
    assert service.requires_login


def test_get_app_state_and_set_keyed_by_username(tmp_path) -> None:
    service, store, _, _ = _build_password_only(tmp_path)
    store.create_user(username="dave", email=None, display_name="Dave")
    service.set_app_state("dave", {"last_document_id": "doc-2", "edit_mode": "raw"})
    state = service.get_app_state("dave")
    assert state is not None
    assert state["last_document_id"] == "doc-2"
    assert state["edit_mode"] == "raw"


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


def _fail(service, *, username="abby", client_ip="10.0.0.1", times=5):
    """Fail *times* sign-ins, enough to put the username over the backoff threshold."""
    for _ in range(times):
        with pytest.raises(LoginFailedError):
            service.login_with_password(username, "wrong", client_ip=client_ip)


class TestRequiresLogin:
    def test_login_is_always_required(self, tmp_path) -> None:
        """No configuration may make a gated route serve an anonymous caller."""
        with_provider, _, _, _ = _build(tmp_path)
        assert with_provider.requires_login

    def test_login_is_required_without_providers_too(self, tmp_path) -> None:
        """The bypass was the absence of a provider; the absence now means password only."""
        service, _, _, _ = _build_password_only(tmp_path)
        assert service.requires_login

    def test_providers_still_reported_for_the_gate(self, tmp_path) -> None:
        service, _, _, _ = _build(tmp_path)
        assert service.providers == ["fake"]

    def test_no_providers_reports_none(self, tmp_path) -> None:
        service, _, _, _ = _build_password_only(tmp_path)
        assert not service.providers


class TestLoginWithPassword:
    def test_correct_password_starts_a_session(self, tmp_path) -> None:
        service, _, sessions, _ = _with_password(tmp_path)
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"
        assert sessions.get("abby") is not None

    def test_username_is_matched_case_insensitively(self, tmp_path) -> None:
        """Usernames normalize on the way in, so typing Abby must not lock anyone out."""
        service, _, _, _ = _with_password(tmp_path)
        assert service.login_with_password("  ABBY  ", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_wrong_password_is_refused(self, tmp_path) -> None:
        service, _, sessions, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError):
            service.login_with_password("abby", "not the password", client_ip="10.0.0.1")
        assert sessions.get("abby") is None

    def test_unknown_username_is_refused(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError):
            service.login_with_password("nobody", _PASSWORD, client_ip="10.0.0.1")

    def test_unknown_username_and_wrong_password_agree(self, tmp_path) -> None:
        """The form must not be able to tell an unknown user from a wrong password."""
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError) as unknown:
            service.login_with_password("nobody", "whatever", client_ip="10.0.0.1")
        with pytest.raises(LoginFailedError) as wrong:
            service.login_with_password("abby", "whatever", client_ip="10.0.0.1")
        assert type(unknown.value) is type(wrong.value)
        assert str(unknown.value) == str(wrong.value)

    def test_account_without_a_password_is_refused(self, tmp_path) -> None:
        """A federated account must not be signable-into with a blank password."""
        service, store, _, _ = _build_password_only(tmp_path)
        store.create_user(username="robin", email=None, display_name="Robin", password_hash=None)
        with pytest.raises(LoginFailedError):
            service.login_with_password("robin", "", client_ip="10.0.0.1")

    def test_blocked_account_is_refused(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.block_user("abby")
        with pytest.raises(LoginFailedError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_deleted_account_is_refused(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        store.soft_delete_user("abby")
        with pytest.raises(LoginFailedError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_blocked_account_is_verified_before_being_refused(self, tmp_path) -> None:
        """Refusing on sight would make "this account is blocked" a free oracle.

        Observed through the backoff rather than the throttle's internals: a blocked
        account only counts a failure if its password was actually verified.
        """
        service, store, _, _ = _with_password(tmp_path)
        store.block_user("abby")
        _fail(service)
        with pytest.raises(RateLimitedError):
            service.login_with_password("abby", "wrong", client_ip="10.0.0.1")

    def test_blocked_account_with_the_right_password_also_looks_like_a_miss(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        store.block_user("abby")
        with pytest.raises(LoginFailedError) as right:
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        assert str(right.value) == "invalid username or password"

    def test_success_records_the_sign_in(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        assert store.get_user("abby")["last_login_at"] is not None

    def test_failure_does_not_record_a_sign_in(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError):
            service.login_with_password("abby", "wrong", client_ip="10.0.0.1")
        assert store.get_user("abby")["last_login_at"] is None

    def test_a_temporary_password_still_signs_in(self, tmp_path) -> None:
        """First-use enforcement gates the routes, it does not refuse the sign-in."""
        service, _, _, _ = _with_password(tmp_path, password="tmp-1", must_change_password=True)
        assert service.login_with_password("abby", "tmp-1", client_ip="10.0.0.1") == "abby"


class TestLoginBackoff:
    def test_first_four_failures_are_not_throttled(self, tmp_path) -> None:
        """A few misses must not lock the owner out of their own account."""
        service, _, _, _ = _with_password(tmp_path)
        for _ in range(4):
            with pytest.raises(LoginFailedError):
                service.login_with_password("abby", "wrong", client_ip="10.0.0.1")

    def test_repeated_failures_eventually_throttle(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        _fail(service)
        with pytest.raises(RateLimitedError):
            service.login_with_password("abby", "wrong", client_ip="10.0.0.1")

    def test_throttling_stops_the_correct_password_too(self, tmp_path) -> None:
        """Otherwise the throttle protects nothing: an attacker just waits for it to lift."""
        service, _, _, _ = _with_password(tmp_path)
        _fail(service)
        with pytest.raises(RateLimitedError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_rate_limited_error_says_how_long_to_wait(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        _fail(service)
        with pytest.raises(RateLimitedError) as limited:
            service.login_with_password("abby", "wrong", client_ip="10.0.0.1")
        assert limited.value.retry_after > 0

    def test_backoff_expires_and_sign_in_works_again(self, tmp_path) -> None:
        service, _, _, clock = _with_password(tmp_path)
        _fail(service)
        with pytest.raises(RateLimitedError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        clock.advance(3600)
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_a_throttled_attempt_does_not_extend_the_backoff(self, tmp_path) -> None:
        """Otherwise waiting out the delay by retrying would restart it."""
        service, _, _, clock = _with_password(tmp_path)
        _fail(service)
        for _ in range(3):
            with pytest.raises(RateLimitedError):
                service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        clock.advance(2)
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_a_success_clears_the_counter(self, tmp_path) -> None:
        """Someone who fumbled twice and then got it right is not left waiting."""
        service, _, _, _ = _with_password(tmp_path)
        for _ in range(3):
            with pytest.raises(LoginFailedError):
                service.login_with_password("abby", "wrong", client_ip="10.0.0.1")
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        for _ in range(3):
            with pytest.raises(LoginFailedError):
                service.login_with_password("abby", "wrong", client_ip="10.0.0.1")
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_throttling_one_username_leaves_another_alone(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        store.create_user(
            username="robin",
            email=None,
            display_name="Robin",
            password_hash=hash_password(_PEPPER, _PASSWORD),
        )
        _fail(service, username="robin", client_ip="10.0.0.2")
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_respelling_the_username_does_not_reset_the_backoff(self, tmp_path) -> None:
        """Otherwise case and whitespace hand out a fresh allowance for the same account."""
        service, _, _, _ = _with_password(tmp_path)
        _fail(service)
        with pytest.raises(RateLimitedError):
            service.login_with_password("  ABBY  ", "wrong", client_ip="10.0.0.1")


class TestChangePassword:
    def test_correct_current_password_replaces_the_hash(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        service.change_password("abby", _PASSWORD, "a brand new password")
        assert service.login_with_password("abby", "a brand new password", client_ip="10.0.0.1") == "abby"

    def test_old_password_stops_working(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        service.change_password("abby", _PASSWORD, "a brand new password")
        with pytest.raises(LoginFailedError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_wrong_current_password_is_refused(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError):
            service.change_password("abby", "not the password", "a brand new password")
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_unknown_user_is_refused(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(LoginFailedError):
            service.change_password("nobody", "whatever", "a brand new password")

    def test_new_password_must_satisfy_the_policy(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(PasswordPolicyError):
            service.change_password("abby", _PASSWORD, "short")
        assert service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1") == "abby"

    def test_policy_failure_leaves_the_old_password_in_force(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        before = store.get_credentials("abby")["password_hash"]
        with pytest.raises(PasswordPolicyError):
            service.change_password("abby", _PASSWORD, "short")
        assert store.get_credentials("abby")["password_hash"] == before

    def test_refuses_to_change_to_the_same_password(self, tmp_path) -> None:
        """It passes the policy and the current-password check, and is still pointless."""
        service, _, _, _ = _with_password(tmp_path)
        with pytest.raises(PasswordUnchangedError):
            service.change_password("abby", _PASSWORD, _PASSWORD)

    def test_changing_clears_the_must_change_flag(self, tmp_path) -> None:
        """Changing the password is exactly what the flag asks for."""
        service, store, _, _ = _with_password(tmp_path, password="tmp-1", must_change_password=True)
        assert store.get_credentials("abby")["must_change_password"] == 1
        service.change_password("abby", "tmp-1", "a brand new password")
        assert store.get_credentials("abby")["must_change_password"] == 0

    def test_changing_stamps_the_credentials(self, tmp_path) -> None:
        """The stamp is what invalidates the sessions this change cannot reach."""
        service, store, _, _ = _with_password(tmp_path)
        service.change_password("abby", _PASSWORD, "a brand new password")
        assert store.get_credentials("abby")["credentials_changed_at"] is not None

    def test_a_change_invalidates_the_current_session(self, tmp_path) -> None:
        """Otherwise a stolen session survives the owner changing the password."""
        service, _, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        service.change_password("abby", _PASSWORD, "a brand new password")
        assert service.resolve_session("abby") is None


class TestResolveSession:
    def test_live_session_resolves(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        assert service.resolve_session("abby") == "abby"

    def test_missing_session_does_not_resolve(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        assert service.resolve_session("abby") is None

    def test_unknown_user_does_not_resolve(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        assert service.resolve_session("nobody") is None

    def test_block_takes_effect_on_a_live_session(self, tmp_path) -> None:
        """The CLI cannot reach the server's sessions, so the stamp is the only lever."""
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.block_user("abby")
        assert service.resolve_session("abby") is None

    def test_delete_takes_effect_on_a_live_session(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.soft_delete_user("abby")
        assert service.resolve_session("abby") is None

    def test_password_reset_takes_effect_on_a_live_session(self, tmp_path) -> None:
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.set_password_hash("abby", _temporary("tmp-2"), must_change_password=True)
        assert service.resolve_session("abby") is None

    def test_unblocking_leaves_nothing_to_restore(self, tmp_path) -> None:
        """Unblocking must not re-open the session the block already invalidated."""
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.block_user("abby")
        store.unblock_user("abby")
        assert service.resolve_session("abby") is None

    def test_session_created_before_an_older_stamp_still_resolves(self, tmp_path) -> None:
        """An account touched long ago must not have its live session refused."""
        service, store, _, clock = _with_password(tmp_path)
        store.set_password_hash("abby", hash_password(_PEPPER, _PASSWORD))
        # A session begun an hour after the stamp is newer than it, so it stands.
        clock.advance(3600)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        assert service.resolve_session("abby") == "abby"

    def test_account_with_no_stamp_resolves(self, tmp_path) -> None:
        """A federated account never has one, and a NULL must not read as 'stale'."""
        service, store, sessions, _ = _build(tmp_path)
        state = service.begin_login("fake").split("state=")[1].split("&")[0]
        username = service.complete_login(state, "code")
        assert store.get_credentials(username)["credentials_changed_at"] is None
        assert sessions.get(username) is not None
        assert service.resolve_session(username) == username

    def test_session_created_in_the_same_instant_as_the_change_is_refused(self, tmp_path) -> None:
        """Equal is refused: at second resolution the two cannot be told apart."""
        service, store, _, _ = _with_password(tmp_path)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        store.set_password_hash("abby", _temporary("tmp-2"))
        assert service.resolve_session("abby") is None


class TestRequiresPasswordChange:
    def test_false_for_a_normal_account(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        assert service.requires_password_change("abby") is False

    def test_true_for_a_temporary_password(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path, password="tmp-1", must_change_password=True)
        assert service.requires_password_change("abby") is True

    def test_false_for_an_unknown_account(self, tmp_path) -> None:
        service, _, _, _ = _with_password(tmp_path)
        assert service.requires_password_change("nobody") is False
