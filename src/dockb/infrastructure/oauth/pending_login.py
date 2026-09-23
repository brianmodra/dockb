"""Server-side memory of in-flight OAuth logins (state → provider + code verifier).

The backend keeps ``state`` → (provider, code_verifier) so the loopback callback
can validate that a login it started is the one completing. Entries expire after
a short TTL. See ``README_auth.md`` §4 (state + PKCE).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from dockb.infrastructure.oauth.pkce import create_code_verifier

_DEFAULT_TTL_SECONDS = 600.0


@dataclass(frozen=True)
class PendingLogin:
    """In-flight login: the provider and the PKCE verifier the callback must present."""

    provider: str
    code_verifier: str
    created_at: float


class PendingLoginStore:
    """Short-lived memory of issued login states."""

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._entries: dict[str, PendingLogin] = {}
        self._ttl_seconds = ttl_seconds

    def issue(self, provider: str) -> tuple[str, str]:
        """Issue a fresh ``(state, code_verifier)`` pair for *provider*."""
        self._expire_stale()
        state = secrets.token_urlsafe(16)
        verifier = create_code_verifier()
        self._entries[state] = PendingLogin(provider=provider, code_verifier=verifier, created_at=time.monotonic())
        return state, verifier

    def _expire_stale(self) -> None:
        """Drop entries older than the TTL so abandoned logins do not accumulate."""
        now = time.monotonic()
        for state, entry in list(self._entries.items()):
            if now - entry.created_at > self._ttl_seconds:
                del self._entries[state]

    def consume(self, state: str) -> PendingLogin | None:
        """Return and forget the login for *state*, unless expired or unknown."""
        entry = self._entries.pop(state, None)
        if entry is None:
            return None
        if time.monotonic() - entry.created_at > self._ttl_seconds:
            return None
        return entry
