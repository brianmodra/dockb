"""Tests for SMTP email delivery settings and messages."""

from __future__ import annotations

import smtplib
import ssl

import pytest

from dockb.infrastructure.email.service import (
    EmailDeliveryError,
    EmailService,
    EmailSettings,
    EmailUnavailableError,
    password_reset_url,
)


class FakeSmtp:
    instances: list[FakeSmtp] = []

    def __init__(self, host: str, port: int, timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_context: ssl.SSLContext | None = None
        self.login_call: tuple[str, str] | None = None
        self.messages: list[tuple[str, str, str]] = []
        self.quit_called = False
        FakeSmtp.instances.append(self)

    def starttls(self, context: ssl.SSLContext | None = None) -> None:
        self.tls_context = context

    def login(self, username: str, password: str) -> None:
        self.login_call = (username, password)

    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        self.messages.append((sender, ",".join(recipients), message))

    def quit(self) -> None:
        self.quit_called = True


class FailingSmtp(FakeSmtp):
    def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
        raise smtplib.SMTPRecipientsRefused({"nobody@example.com": (550, "refused")})


def settings(**overrides: object) -> EmailSettings:
    values: dict[str, object] = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "dockb",
        "password": "secret",
        "use_tls": True,
        "from_address": "DockB <no-reply@example.com>",
        "public_url": "http://localhost:8000",
    }
    values.update(overrides)
    return EmailSettings(**values)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def reset_fake_smtp() -> None:
    FakeSmtp.instances = []


def test_settings_from_env_reads_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "DOCKB_SMTP_HOST": "mail.example.com",
        "DOCKB_SMTP_PORT": "465",
        "DOCKB_SMTP_USERNAME": "writer",
        "DOCKB_SMTP_PASSWORD": "hunter2",
        "DOCKB_SMTP_USE_TLS": "false",
        "DOCKB_EMAIL_FROM": "DockB <dockb@example.com>",
        "DOCKB_PUBLIC_URL": "https://dockb.example.com/",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    result = EmailSettings.from_env()
    assert result == EmailSettings(
        host="mail.example.com",
        port=465,
        username="writer",
        password="hunter2",
        use_tls=False,
        from_address="DockB <dockb@example.com>",
        public_url="https://dockb.example.com/",
    )


def test_settings_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DOCKB_SMTP_HOST",
        "DOCKB_SMTP_PORT",
        "DOCKB_SMTP_USERNAME",
        "DOCKB_SMTP_PASSWORD",
        "DOCKB_SMTP_USE_TLS",
        "DOCKB_EMAIL_FROM",
        "DOCKB_PUBLIC_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    result = EmailSettings.from_env()
    assert result == EmailSettings(
        host="",
        port=587,
        username="",
        password="",
        use_tls=True,
        from_address="",
        public_url="http://localhost:8000",
    )


def test_settings_configured_requires_host_and_from(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKB_SMTP_HOST", raising=False)
    monkeypatch.delenv("DOCKB_EMAIL_FROM", raising=False)
    assert not EmailSettings.from_env().configured
    monkeypatch.setenv("DOCKB_SMTP_HOST", "smtp.example.com")
    assert not EmailSettings.from_env().configured
    monkeypatch.setenv("DOCKB_EMAIL_FROM", "dockb@example.com")
    assert EmailSettings.from_env().configured


def test_password_reset_url_encodes_token_and_targets_editor() -> None:
    url = password_reset_url("https://dockb.example.com/", "a/b+c")
    assert url == "https://dockb.example.com/editor/?reset-password=a%2Fb%2Bc"


def test_send_password_reset_uses_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dockb.infrastructure.email.service.smtplib.SMTP", FakeSmtp)
    service = EmailService(settings())
    service.send_password_reset("writer@example.com", "reset-token")
    smtp = FakeSmtp.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.tls_context is not None
    assert smtp.tls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.login_call == ("dockb", "secret")
    assert smtp.quit_called
    assert len(smtp.messages) == 1
    sender, recipients, message = smtp.messages[0]
    assert sender == "DockB <no-reply@example.com>"
    assert recipients == "writer@example.com"
    assert "http://localhost:8000/editor/?reset-password=reset-token" in message
    assert "24 hours" in message


def test_send_email_otp_includes_code_and_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dockb.infrastructure.email.service.smtplib.SMTP", FakeSmtp)
    EmailService(settings()).send_email_otp("writer@example.com", "123456")
    message = FakeSmtp.instances[0].messages[0][2]
    assert "123456" in message
    assert "5 minutes" in message


def test_send_without_configuration_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dockb.infrastructure.email.service.smtplib.SMTP", FakeSmtp)
    service = EmailService(settings(host="", from_address=""))
    with pytest.raises(EmailUnavailableError):
        service.send("writer@example.com", "Subject", "Body")
    assert not FakeSmtp.instances


def test_send_without_tls_does_not_start_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dockb.infrastructure.email.service.smtplib.SMTP", FakeSmtp)
    EmailService(settings(use_tls=False, username="", password="")).send("writer@example.com", "Subject", "Body")
    smtp = FakeSmtp.instances[0]
    assert smtp.tls_context is None
    assert smtp.login_call is None


def test_send_wraps_smtp_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dockb.infrastructure.email.service.smtplib.SMTP", FailingSmtp)
    with pytest.raises(EmailDeliveryError) as caught:
        EmailService(settings()).send("writer@example.com", "Subject", "Body")
    assert "nobody@example.com" not in str(caught.value)
    assert FakeSmtp.instances[0].quit_called


def test_message_uses_email_message_headers() -> None:
    message = EmailService._message("writer@example.com", "Reset your password", "Body")
    assert "To: writer@example.com" in message
    assert "Subject: Reset your password" in message
    assert "\n\nBody" in message
