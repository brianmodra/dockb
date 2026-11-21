"""SMTP email delivery for DockB account recovery and verification."""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import quote

_DEFAULT_PUBLIC_URL = "http://localhost:8000"
_DEFAULT_SMTP_PORT = 587
_FALSE_VALUES = {"0", "false", "no", "off"}


class EmailUnavailableError(RuntimeError):
    """SMTP is not configured, so no email can be sent."""


class EmailDeliveryError(RuntimeError):
    """The configured SMTP server refused or failed a send."""


@dataclass(frozen=True)
class EmailSettings:
    """SMTP and public-link settings resolved from the environment."""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_address: str
    public_url: str

    @property
    def configured(self) -> bool:
        """Whether enough settings exist to attempt a send."""
        return bool(self.host.strip() and self.from_address.strip())

    @classmethod
    def from_env(cls) -> EmailSettings:
        """Read SMTP settings from the process environment."""
        return cls(
            host=os.environ.get("DOCKB_SMTP_HOST", "").strip(),
            port=int(os.environ.get("DOCKB_SMTP_PORT") or _DEFAULT_SMTP_PORT),
            username=os.environ.get("DOCKB_SMTP_USERNAME", "").strip(),
            password=os.environ.get("DOCKB_SMTP_PASSWORD", ""),
            use_tls=os.environ.get("DOCKB_SMTP_USE_TLS", "true").strip().lower() not in _FALSE_VALUES,
            from_address=os.environ.get("DOCKB_EMAIL_FROM", "").strip(),
            public_url=os.environ.get("DOCKB_PUBLIC_URL", "").strip() or _DEFAULT_PUBLIC_URL,
        )


def password_reset_url(public_url: str, token: str) -> str:
    """Build the absolute editor URL carried in a password-reset email."""
    return f"{public_url.rstrip('/')}/editor/?reset-password={quote(token, safe='')}"


class EmailService:
    """Sends DockB's small set of account emails over SMTP."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        """Whether this service can attempt a send."""
        return self._settings.configured

    def send(self, recipient: str, subject: str, body: str) -> None:
        """Send one plain-text email."""
        if not self._settings.configured:
            raise EmailUnavailableError("email is not configured")
        smtp: smtplib.SMTP | None = None
        try:
            smtp = smtplib.SMTP(self._settings.host, self._settings.port, timeout=10)
            if self._settings.use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if self._settings.username:
                smtp.login(self._settings.username, self._settings.password)
            smtp.sendmail(self._settings.from_address, [recipient], self._message(recipient, subject, body, self._settings.from_address))
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError("email delivery failed") from exc
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except (smtplib.SMTPException, OSError):
                    pass

    def send_password_reset(self, recipient: str, token: str) -> None:
        """Send the password-reset link for *token*."""
        link = password_reset_url(self._settings.public_url, token)
        body = f"Reset your DockB password within 24 hours:\n\n{link}\n\nIf you did not request this, ignore this email.\n"
        self.send(recipient, "Reset your DockB password", body)

    def send_email_otp(self, recipient: str, code: str) -> None:
        """Send a five-minute email one-time code."""
        body = f"Your DockB sign-in code is {code}.\n\nIt expires in 5 minutes. If you did not request it, ignore this email.\n"
        self.send(recipient, "Your DockB sign-in code", body)

    @staticmethod
    def _message(recipient: str, subject: str, body: str, sender: str | None = None) -> str:
        message = EmailMessage()
        message["To"] = recipient
        message["Subject"] = subject
        if sender:
            message["From"] = sender
        message.set_content(body)
        return message.as_string()
