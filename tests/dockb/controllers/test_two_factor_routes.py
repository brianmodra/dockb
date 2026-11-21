"""HTTP contract tests for recovery and two-factor auth routes."""

from __future__ import annotations

import logging

import pyotp
import pytest
from fastapi.testclient import TestClient

from dockb import composition
from dockb.app_factory import create_app
from dockb.controllers.auth import set_auth_service
from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.email.service import EmailDeliveryError
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.passwords import hash_password, pepper_from
from dockb.services.auth_service import AuthService

_SECRET = "a-server-secret"
_PASSWORD = "correct horse battery"


class _Email:  # pylint: disable=too-few-public-methods
    def __init__(self, *, configured: bool = True, fail: bool = False) -> None:
        self.configured = configured
        self.fail = fail
        self.password_resets: list[tuple[str, str]] = []
        self.otps: list[tuple[str, str]] = []

    def send_password_reset(self, recipient: str, token: str) -> None:
        if self.fail:
            raise EmailDeliveryError("email delivery failed")
        self.password_resets.append((recipient, token))

    def send_email_otp(self, recipient: str, code: str) -> None:
        if self.fail:
            raise EmailDeliveryError("email delivery failed")
        self.otps.append((recipient, code))


def _service(tmp_path, *, email: _Email | None = None):
    store = AccountStore(base_dir=tmp_path, secret=_SECRET)
    store.create_user(
        "abby",
        email="abby@example.com",
        display_name="Abby",
        password_hash=hash_password(pepper_from(_SECRET), _PASSWORD),
    )
    return (
        AuthService(
            {},
            PendingLoginStore(),
            store,
            SessionManager(),
            SessionSigner(_SECRET, ttl_hours=2),
            pepper=pepper_from(_SECRET),
            email_service=email if email is not None else _Email(),
        ),
        store,
    )


@pytest.fixture()
def client(tmp_path):
    service, store = _service(tmp_path)
    set_auth_service(service)
    app = create_app()
    yield TestClient(app), service, store
    set_auth_service(None)


def _sign_in(client: TestClient):
    return client.post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD})


def _password_challenge(client: TestClient) -> dict[str, str]:
    response = _sign_in(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["two_factor_required"] is True
    return body


def _enroll_totp(client: TestClient) -> str:
    response = client.post("/api/auth/2fa/enroll", json={"method": "totp"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "totp"
    assert body["provisioning_uri"]
    confirm = client.post("/api/auth/2fa/confirm", json={"method": "totp", "code": pyotp.TOTP(body["secret"]).now()})
    assert confirm.status_code == 200, confirm.text
    return body["secret"]


class TestPasswordResetRoutes:
    def test_composition_wires_email_delivery(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCKB_SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("DOCKB_EMAIL_FROM", "dockb@example.com")
        store = AccountStore(base_dir=tmp_path, secret=_SECRET)

        service = composition._build_auth_service(store, _SECRET)  # pylint: disable=protected-access

        assert service.email_available

    def test_request_sends_a_link_in_the_background(self, tmp_path) -> None:
        email = _Email()
        service, _ = _service(tmp_path, email=email)
        set_auth_service(service)
        app = create_app()

        response = TestClient(app).post("/api/auth/password-reset/request", json={"email": "abby@example.com"})

        assert response.status_code == 202, response.text
        assert response.json()["status"] == "accepted"
        assert len(email.password_resets) == 1
        set_auth_service(None)

    def test_unknown_email_gets_the_same_answer(self, tmp_path) -> None:
        email = _Email()
        service, _ = _service(tmp_path, email=email)
        set_auth_service(service)
        app = create_app()

        response = TestClient(app).post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})

        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}
        assert not email.password_resets
        set_auth_service(None)

    def test_unconfigured_email_is_reported_before_the_request(self, tmp_path) -> None:
        service, _ = _service(tmp_path, email=_Email(configured=False))
        set_auth_service(service)
        app = create_app()

        response = TestClient(app).post("/api/auth/password-reset/request", json={"email": "abby@example.com"})

        assert response.status_code == 503
        assert response.json()["detail"] == "email_unavailable"
        set_auth_service(None)

    def test_background_email_failure_is_logged(self, tmp_path, caplog: pytest.LogCaptureFixture) -> None:
        service, _ = _service(tmp_path, email=_Email(fail=True))
        set_auth_service(service)
        app = create_app()

        with caplog.at_level(logging.WARNING):
            response = TestClient(app).post("/api/auth/password-reset/request", json={"email": "abby@example.com"})

        assert response.status_code == 202
        assert "password reset email could not be sent" in caplog.text
        set_auth_service(None)

    def test_confirm_changes_the_password(self, client) -> None:
        test_client, service, _ = client
        email = service._email  # pylint: disable=protected-access
        test_client.post("/api/auth/password-reset/request", json={"email": "abby@example.com"})
        token = email.password_resets[0][1]

        response = test_client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "a brand new password"},
        )

        assert response.status_code == 200, response.text
        assert test_client.post("/api/auth/login/password", json={"username": "abby", "password": _PASSWORD}).status_code == 401
        assert (
            test_client.post(
                "/api/auth/login/password",
                json={"username": "abby", "password": "a brand new password"},
            ).status_code
            == 200
        )

    def test_confirm_rejects_a_bad_token(self, client) -> None:
        test_client, _, _ = client
        response = test_client.post(
            "/api/auth/password-reset/confirm",
            json={"token": "never-issued", "new_password": "a brand new password"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_reset_token"


class TestTwoFactorEnrollmentRoutes:
    def test_totp_enrollment_and_me_state(self, client) -> None:
        test_client, service, _ = client
        _sign_in(test_client)
        _enroll_totp(test_client)

        me = test_client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["two_factor_enabled"] is True
        assert me.json()["two_factor_method"] == "totp"

        challenge = _password_challenge(test_client)
        assert challenge["two_factor_enabled"] is True
        assert challenge["two_factor_method"] == "totp"
        assert challenge["method"] == "totp"
        assert service.two_factor_method("abby") == "totp"

    def test_email_enrollment_and_resend(self, client) -> None:
        test_client, service, _ = client
        _sign_in(test_client)
        email = service._email  # pylint: disable=protected-access

        enroll = test_client.post("/api/auth/2fa/enroll", json={"method": "email"})
        assert enroll.status_code == 200
        assert len(email.otps) == 1
        code = email.otps[-1][1]
        confirm = test_client.post("/api/auth/2fa/confirm", json={"method": "email", "code": code})
        assert confirm.status_code == 200, confirm.text

        challenge = _password_challenge(test_client)
        sent = len(email.otps)
        resend = test_client.post("/api/auth/2fa/resend")
        assert resend.status_code == 200
        assert len(email.otps) == sent + 1

        verify = test_client.post(
            "/api/auth/2fa/verify",
            json={"challenge": challenge["challenge"], "code": email.otps[-1][1]},
        )
        assert verify.status_code == 200, verify.text
        assert "dockb_session=" in verify.headers["set-cookie"]

    def test_email_delivery_failure_is_reported(self, tmp_path) -> None:
        service, _ = _service(tmp_path, email=_Email(fail=True))
        set_auth_service(service)
        app = create_app()
        test_client = TestClient(app)
        _sign_in(test_client)

        response = test_client.post("/api/auth/2fa/enroll", json={"method": "email"})

        assert response.status_code == 503
        assert response.json()["detail"] == "email_delivery_failed"
        set_auth_service(None)

    def test_enrollment_requires_a_session(self, client) -> None:
        test_client, _, _ = client
        response = test_client.post("/api/auth/2fa/enroll", json={"method": "totp"})
        assert response.status_code == 401


class TestTwoFactorVerifyRoute:
    def test_login_without_two_factor_reports_it_disabled(self, client) -> None:
        test_client, _, _ = client
        response = _sign_in(test_client)

        assert response.status_code == 200
        assert response.json()["two_factor_enabled"] is False
        assert response.json()["two_factor_method"] is None

    def test_a_valid_code_sets_the_session_cookie(self, client) -> None:
        test_client, _, _ = client
        _sign_in(test_client)
        secret = _enroll_totp(test_client)
        challenge = _password_challenge(test_client)

        response = test_client.post(
            "/api/auth/2fa/verify",
            json={"challenge": challenge["challenge"], "code": pyotp.TOTP(secret).now()},
        )

        assert response.status_code == 200, response.text
        assert "dockb_session=" in response.headers["set-cookie"]
        assert response.json()["user"]["username"] == "abby"
        assert test_client.get("/api/auth/me").status_code == 200

    def test_a_wrong_code_is_refused(self, client) -> None:
        test_client, _, _ = client
        _sign_in(test_client)
        _enroll_totp(test_client)
        challenge = _password_challenge(test_client)

        response = test_client.post(
            "/api/auth/2fa/verify",
            json={"challenge": challenge["challenge"], "code": "not-a-code"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_two_factor_code"

    def test_a_blocked_account_cannot_finish_a_challenge(self, client) -> None:
        test_client, _, store = client
        _sign_in(test_client)
        secret = _enroll_totp(test_client)
        challenge = _password_challenge(test_client)
        store.block_user("abby")

        response = test_client.post(
            "/api/auth/2fa/verify",
            json={"challenge": challenge["challenge"], "code": pyotp.TOTP(secret).now()},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "invalid_two_factor_code"
