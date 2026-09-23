"""Session cookie signing — a Fernet token (signed + time-limited) over the user id.

The token embeds its own timestamp and an HMAC, so the backend can verify both the
issuer (``DOCKB_SECRET_KEY``) and the expiry without server-side session storage.
The cookie is ``HttpOnly``; see ``README_auth.md`` §4.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_DEFAULT_TTL_HOURS = 48


def _derive_key(secret: str) -> bytes:
    digest = hashlib.sha256(f"{secret}::session-cookie".encode()).digest()
    return base64.urlsafe_b64encode(digest)


class SessionSigner:
    """Signs and verifies the backend's own HttpOnly session-cookie value."""

    def __init__(self, secret: str, ttl_hours: int = _DEFAULT_TTL_HOURS) -> None:
        self._fernet = Fernet(_derive_key(secret))
        self._ttl_seconds = ttl_hours * 3600

    @property
    def ttl_seconds(self) -> int:
        """Cookie max-age / validity in seconds."""
        return self._ttl_seconds

    def sign(self, user_id: str) -> str:
        """Return a signed, expiring token carrying *user_id*."""
        return self._fernet.encrypt(user_id.encode("utf-8")).decode("ascii")

    def verify(self, token: str) -> str | None:
        """Return the user id if *token* is ours and unexpired, else None."""
        if self._ttl_seconds <= 0:
            return None
        try:
            payload = self._fernet.decrypt(token.encode("ascii"), ttl=self._ttl_seconds)
        except InvalidToken:
            return None
        return payload.decode("utf-8")
