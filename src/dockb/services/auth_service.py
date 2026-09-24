"""OAuth login flow for the backend-as-confidential-client (Authorization Code + PKCE).

``AuthService`` is the thin orchestration behind the auth routes: issue a consent
URL (remembering state + PKCE verifier), complete the loopback callback (validate
state, exchange the code, upsert the account, encrypt the refresh token, start the
server-side session), and hand out the signed session cookie.

With no provider configured (``providers={}``) the service runs in **local mode**:
there is no login step, the identity is the OS username (``local_username()``), and
``ensure_local_user`` gives it a ``users`` row lazily. See ``README_auth.md``.
"""

from __future__ import annotations

import getpass
import os

from dockb.infrastructure.accounts.store import AccountStore
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.oauth.provider import OAuthProvider, OAuthProviderError
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager


class UnknownProviderError(ValueError):
    """Raised when a login is requested for a provider that is not configured."""


class InvalidLoginStateError(ValueError):
    """Raised when the callback presents an unknown, stale, or forged state."""


class AuthService:
    """Orchestrates the login flow and hands out backend session cookies."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        # five collaborating singletons, injected explicitly for composition
        self,
        providers: dict[str, OAuthProvider],
        pending_store: PendingLoginStore,
        account_store: AccountStore,
        session_manager: SessionManager,
        signer: SessionSigner,
    ) -> None:
        self._providers = providers
        self._pending = pending_store
        self._accounts = account_store
        self._sessions = session_manager
        self._signer = signer

    @property
    def requires_login(self) -> bool:
        """Whether OAuth login is required (True) or local mode is active (False)."""
        return bool(self._providers)

    @property
    def providers(self) -> list[str]:
        """The names of the configured OAuth providers (empty in local mode)."""
        return list(self._providers)

    def local_username(self) -> str:
        """The OS username that is the local-mode identity ($USER, else getpass)."""
        return os.environ.get("USER") or getpass.getuser()

    def ensure_local_user(self, username: str) -> str:
        """Return *username*, creating a minimal ``users`` row when it is absent."""
        return self._accounts.get_or_create_local_user(username)

    def begin_login(self, provider: str) -> str:
        """Return the *provider*'s consent URL, remembering state + verifier."""
        oauth_provider = self._providers.get(provider)
        if oauth_provider is None:
            raise UnknownProviderError(f"provider not configured: {provider}")
        state, verifier = self._pending.issue(provider)
        return oauth_provider.authorization_url(state, verifier)

    def complete_login(self, state: str, code: str) -> str:
        """Complete the callback: verify state, exchange, upsert, start session. Returns the username."""
        pending = self._pending.consume(state)
        if pending is None:
            raise InvalidLoginStateError("unknown or expired login state")
        oauth_provider = self._providers.get(pending.provider)
        if oauth_provider is None:
            raise InvalidLoginStateError(f"provider not configured: {pending.provider}")
        try:
            tokens = oauth_provider.exchange_code(code, pending.code_verifier)
            profile = oauth_provider.fetch_profile(tokens.access_token)
        except OAuthProviderError as exc:
            raise InvalidLoginStateError(str(exc)) from exc
        user_id = self._accounts.upsert_provider_user(
            provider=profile.provider,
            provider_account_id=profile.provider_account_id,
            username=profile.username,
            email=profile.email,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
            token=tokens.refresh_token,
            expires_at=tokens.expires_at.isoformat() if tokens.expires_at is not None else None,
        )
        self._sessions.create(user_id)
        return user_id

    def session_cookie(self, user_id: str) -> str:
        """Return a signed session cookie for *user_id*."""
        return self._signer.sign(user_id)

    def authenticate_cookie(self, token: str) -> str | None:
        """Return the user id a session cookie belongs to, or None."""
        return self._signer.verify(token)

    def get_user(self, user_id: str) -> dict[str, object] | None:
        """Return the stored profile for *user_id*, or None."""
        return self._accounts.get_user(user_id)

    def session_for(self, user_id: str) -> object | None:
        """Return the live SessionContext for *user_id*, possibly None (e.g. after restart)."""
        return self._sessions.get(user_id)

    def get_app_state(self, user_id: str) -> dict[str, object] | None:
        """Return the user's stored app-state row, or None."""
        return self._accounts.get_app_state(user_id)

    def set_app_state(self, user_id: str, state: dict[str, object]) -> None:
        """Upsert the user's app state as a whole."""
        self._accounts.set_app_state(user_id, state)

    @property
    def session_ttl_seconds(self) -> int:
        """How long a session cookie stays valid."""
        return self._signer.ttl_seconds
