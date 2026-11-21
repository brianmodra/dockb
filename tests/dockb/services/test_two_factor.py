"""Tests for password recovery and two-factor sign-in flows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.email.service import EmailUnavailableError
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.passwords import PasswordPolicyError, hash_password, pepper_from
from dockb.services.auth_service import (
    AuthService,
    InvalidResetTokenError,
    InvalidTwoFactorError,
)

_SECRET = "a-server-secret"
_PEPPER = pepper_from(_SECRET)
_PASSWORD = "correct horse battery"


class _Clock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class _Email:  # pylint: disable=too-few-public-methods
    def __init__(self) -> None:
        self.password_resets: list[tuple[str, str]] = []
        self.otps: list[tuple[str, str]] = []

    def send_password_reset(self, recipient: str, token: str) -> None:
        self.password_resets.append((recipient, token))

    def send_email_otp(self, recipient: str, code: str) -> None:
        self.otps.append((recipient, code))


def _build(tmp_path, *, with_email: bool = True, account_email: str | None = "abby@example.com"):
    clock = _Clock()
    store = AccountStore(base_dir=tmp_path, secret=_SECRET)
    sessions = SessionManager(clock)
    email = _Email() if with_email else None
    service = AuthService(
        {},
        PendingLoginStore(),
        store,
        sessions,
        SessionSigner(_SECRET, ttl_hours=2),
        pepper=_PEPPER,
        email_service=email,
        clock=clock,
    )
    store.create_user(
        username="abby",
        email=account_email,
        display_name="Abby",
        password_hash=hash_password(_PEPPER, _PASSWORD),
    )
    return service, store, sessions, clock, email


def _enroll_totp(service) -> str:
    enrollment = service.begin_two_factor_enrollment("abby", "totp")
    assert enrollment.secret is not None
    assert enrollment.provisioning_uri is not None
    service.confirm_two_factor_enrollment("abby", "totp", pyotp.TOTP(enrollment.secret).now())
    return enrollment.secret


def _enroll_email(service, email) -> None:
    service.begin_two_factor_enrollment("abby", "email")
    service.confirm_two_factor_enrollment("abby", "email", email.otps[-1][1])


class TestTotpLogin:
    def test_password_check_returns_a_challenge_without_a_session(self, tmp_path) -> None:
        service, store, sessions, _, _ = _build(tmp_path)
        secret = _enroll_totp(service)

        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

        assert result.username == "abby"
        assert result.requires_two_factor
        assert result.method == "totp"
        assert result.challenge
        assert sessions.get("abby") is None
        assert store.get_user("abby")["last_login_at"] is None

        assert service.complete_two_factor_login(result.challenge, pyotp.TOTP(secret).now()) == "abby"
        assert sessions.get("abby") is not None
        assert store.get_user("abby")["last_login_at"] is not None

    def test_wrong_code_keeps_the_challenge_usable(self, tmp_path) -> None:
        service, _, sessions, _, _ = _build(tmp_path)
        secret = _enroll_totp(service)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, "not-a-code")
        assert sessions.get("abby") is None

        assert service.complete_two_factor_login(result.challenge, pyotp.TOTP(secret).now()) == "abby"
        assert sessions.get("abby") is not None

    def test_a_completed_challenge_cannot_be_reused(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path)
        secret = _enroll_totp(service)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        code = pyotp.TOTP(secret).now()
        service.complete_two_factor_login(result.challenge, code)

        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, code)

    def test_an_expired_challenge_is_refused(self, tmp_path) -> None:
        service, _, _, clock, _ = _build(tmp_path)
        secret = _enroll_totp(service)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        clock.advance(301)

        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, pyotp.TOTP(secret).now())


class TestEmailOtpLogin:
    def test_login_sends_a_code_and_waits_for_it(self, tmp_path) -> None:
        service, _, sessions, _, email = _build(tmp_path)
        _enroll_email(service, email)
        email.otps.clear()

        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

        assert result.requires_two_factor
        assert result.method == "email"
        assert result.challenge
        assert len(email.otps) == 1
        assert email.otps[-1][0] == "abby@example.com"
        assert sessions.get("abby") is None

        assert service.complete_two_factor_login(result.challenge, email.otps[-1][1]) == "abby"
        assert sessions.get("abby") is not None

    def test_wrong_code_can_be_retried_until_the_limit(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        _enroll_email(service, email)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        code = email.otps[-1][1]

        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, "wrong")
        assert service.complete_two_factor_login(result.challenge, code) == "abby"

    def test_too_many_wrong_codes_refuse_the_right_one(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        _enroll_email(service, email)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        code = email.otps[-1][1]

        for _ in range(5):
            with pytest.raises(InvalidTwoFactorError):
                service.complete_two_factor_login(result.challenge, "wrong")
        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, code)

    def test_an_expired_code_is_refused(self, tmp_path) -> None:
        service, _, _, clock, email = _build(tmp_path)
        _enroll_email(service, email)
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        code = email.otps[-1][1]
        clock.advance(301)

        with pytest.raises(InvalidTwoFactorError):
            service.complete_two_factor_login(result.challenge, code)


class TestTwoFactorEnrollment:
    def test_totp_enrollment_needs_a_current_code(self, tmp_path) -> None:
        service, store, _, _, _ = _build(tmp_path)
        enrollment = service.begin_two_factor_enrollment("abby", "totp")
        assert enrollment.secret

        with pytest.raises(InvalidTwoFactorError):
            service.confirm_two_factor_enrollment("abby", "totp", "wrong")
        assert service.two_factor_method("abby") is None

        service.confirm_two_factor_enrollment("abby", "totp", pyotp.TOTP(enrollment.secret).now())
        assert service.two_factor_method("abby") == "totp"
        assert store.get_two_factor_state("abby")["totp_secret"] == enrollment.secret

    def test_email_enrollment_uses_the_mailed_code(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        service.begin_two_factor_enrollment("abby", "email")
        assert email.otps[-1][0] == "abby@example.com"

        service.confirm_two_factor_enrollment("abby", "email", email.otps[-1][1])
        assert service.two_factor_method("abby") == "email"

    def test_an_unknown_method_is_refused(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path)
        with pytest.raises(ValueError):
            service.begin_two_factor_enrollment("abby", "sms")

    def test_a_stale_enrollment_is_refused(self, tmp_path) -> None:
        service, _, _, clock, _ = _build(tmp_path)
        enrollment = service.begin_two_factor_enrollment("abby", "totp")
        assert enrollment.secret
        clock.advance(301)

        with pytest.raises(InvalidTwoFactorError):
            service.confirm_two_factor_enrollment("abby", "totp", pyotp.TOTP(enrollment.secret).now())
        assert service.two_factor_method("abby") is None

    def test_disabling_removes_all_two_factor_state(self, tmp_path) -> None:
        service, store, _, _, _ = _build(tmp_path)
        _enroll_totp(service)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

        service.disable_two_factor("abby")

        assert service.two_factor_method("abby") is None
        assert store.get_two_factor_state("abby")["totp_secret"] is None
        result = service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        assert not result.requires_two_factor

    def test_unknown_account_has_no_method(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path)
        assert service.two_factor_method("nobody") is None


class TestPasswordReset:
    def test_request_mails_a_token_but_says_nothing_for_an_unknown_email(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)

        service.request_password_reset("  ABBY@EXAMPLE.COM  ")
        service.request_password_reset("nobody@example.com")

        assert len(email.password_resets) == 1
        assert email.password_resets[0][0] == "abby@example.com"

    def test_a_valid_token_replaces_the_password_once(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        service.request_password_reset("abby@example.com")
        token = email.password_resets[0][1]

        service.reset_password(token, "a brand new password")

        assert service.login_with_password("abby", "a brand new password", client_ip="10.0.0.1").username == "abby"
        with pytest.raises(InvalidResetTokenError):
            service.reset_password(token, "another brand new password")

    def test_an_expired_token_is_refused(self, tmp_path) -> None:
        service, _, _, clock, email = _build(tmp_path)
        service.request_password_reset("abby@example.com")
        token = email.password_resets[0][1]
        clock.advance(86401)

        with pytest.raises(InvalidResetTokenError):
            service.reset_password(token, "a brand new password")

    def test_a_bad_new_password_does_not_burn_the_token(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        service.request_password_reset("abby@example.com")
        token = email.password_resets[0][1]

        with pytest.raises(PasswordPolicyError):
            service.reset_password(token, "short")
        service.reset_password(token, "a brand new password")

    def test_resetting_cancels_two_factor_and_live_sessions(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        _enroll_totp(service)
        service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")
        service.request_password_reset("abby@example.com")

        service.reset_password(email.password_resets[0][1], "a brand new password")

        assert service.two_factor_method("abby") is None
        assert service.resolve_session("abby") is None
        result = service.login_with_password("abby", "a brand new password", client_ip="10.0.0.1")
        assert not result.requires_two_factor

    def test_resetting_cancels_a_pending_enrollment(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        enrollment = service.begin_two_factor_enrollment("abby", "totp")
        assert enrollment.secret is not None
        service.request_password_reset("abby@example.com")

        service.reset_password(email.password_resets[0][1], "a brand new password")

        with pytest.raises(InvalidTwoFactorError):
            service.confirm_two_factor_enrollment("abby", "totp", pyotp.TOTP(enrollment.secret).now())
        assert service.two_factor_method("abby") is None


class TestEmailUnavailable:
    def test_reset_needs_email_delivery(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path, with_email=False)
        with pytest.raises(EmailUnavailableError):
            service.request_password_reset("abby@example.com")

    def test_email_enrollment_needs_email_delivery(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path, with_email=False)
        with pytest.raises(EmailUnavailableError):
            service.begin_two_factor_enrollment("abby", "email")

    def test_email_factor_login_needs_email_delivery(self, tmp_path) -> None:
        service, store, _, _, _ = _build(tmp_path, with_email=False)
        store.set_two_factor("abby", method="email")

        with pytest.raises(EmailUnavailableError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_email_factor_login_needs_an_account_email(self, tmp_path) -> None:
        service, store, _, _, _ = _build(tmp_path, account_email=None)
        store.set_two_factor("abby", method="email")

        with pytest.raises(EmailUnavailableError):
            service.login_with_password("abby", _PASSWORD, client_ip="10.0.0.1")

    def test_email_enrollment_needs_an_account_email(self, tmp_path) -> None:
        service, _, _, _, _ = _build(tmp_path, account_email=None)

        with pytest.raises(EmailUnavailableError):
            service.begin_two_factor_enrollment("abby", "email")


class TestEnrollmentMethodBinding:  # pylint: disable=too-few-public-methods
    def test_confirming_a_different_method_is_refused(self, tmp_path) -> None:
        service, _, _, _, email = _build(tmp_path)
        service.begin_two_factor_enrollment("abby", "email")

        with pytest.raises(InvalidTwoFactorError):
            service.confirm_two_factor_enrollment("abby", "totp", email.otps[-1][1])
        assert service.two_factor_method("abby") is None
