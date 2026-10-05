"""Sign-in for the backend: password login, the OAuth loopback flow, and session cookies.

``AuthService`` is the thin orchestration behind the auth routes. For a password it
verifies the Argon2id hash and starts the server-side session. For a provider it issues a
consent URL (remembering state + PKCE verifier), completes the loopback callback (validate
state, exchange the code, upsert the account, encrypt the refresh token, start the
server-side session), and hands out the signed session cookie.

**Every request requires a sign-in.** There is no mode in which an identity is served
without one — see ``README_auth.md`` §6. The single signing-in identity is a username and
password; OAuth providers are an alternative way to reach an account, not an alternative to
the gate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from dockb.infrastructure.accounts.store import AccountStore, normalize_username
from dockb.infrastructure.oauth.pending_login import PendingLoginStore
from dockb.infrastructure.oauth.provider import OAuthProvider, OAuthProviderError
from dockb.infrastructure.session.login_throttle import LoginThrottle
from dockb.infrastructure.session.session_cookie import SessionSigner
from dockb.infrastructure.session.session_manager import SessionManager
from dockb.passwords import DUMMY_HASH, hash_password, verify_password

# One message for every refusal. What actually went wrong stays in the server's log; the
# caller is told the same thing whether the username is unknown, the password is wrong,
# or the account is blocked or deleted.
_LOGIN_REFUSED = "invalid username or password"


class UnknownProviderError(ValueError):
    """Raised when a login is requested for a provider that is not configured."""


class InvalidLoginStateError(ValueError):
    """Raised when the callback presents an unknown, stale, or forged state."""


class LoginFailedError(Exception):
    """Raised when a sign-in is refused, for any reason the caller must not be told.

    One exception for a wrong password, an unknown username, a blocked or deleted
    account, and an account with no password at all. The reason changes what the caller
    does next, but it is not something the form is allowed to reveal, so it lives in the
    message for the log and never in the response.
    """


class PasswordUnchangedError(Exception):
    """Raised when a password change asks for the password already in force.

    Separate from LoginFailedError because it is not a failed authentication: the caller
    proved who they are and then asked for something pointless, so the route answers
    differently and says why.
    """


class RateLimitedError(Exception):
    """Raised when a sign-in arrives while a backoff is still in force.

    Distinct from LoginFailedError so the caller learns whether to slow down or to
    re-prompt, and carries the remaining seconds so the route can say how long.
    """

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"too many failed attempts; retry in {retry_after:.0f}s")
        self.retry_after = retry_after


def _stored_hash(credentials: dict[str, Any] | None) -> str:
    """Return the hash to verify against, or the dummy when there is no account.

    An unknown username and an account with no password both verify against the dummy, so
    every refusal costs one Argon2 evaluation and none of them is distinguishable by how
    long it took.
    """
    if credentials is None:
        return DUMMY_HASH
    return credentials["password_hash"] or DUMMY_HASH


def _may_sign_in(credentials: dict[str, Any]) -> bool:
    """Whether the account's lifecycle state allows a sign-in."""
    return not credentials["blocked_at"] and not credentials["deleted_at"]


def _credentials_changed_since(stamp: str | None, session_started: datetime) -> bool:
    """Whether the credentials were stamped at or after *session_started*.

    Read as instants rather than compared as strings, because one comes from SQLite and
    the other from the session clock. Equal counts as changed: at second resolution the
    two cannot be told apart, and a session created in the same instant as a reset must
    not survive it. A NULL stamp means no credential has ever been recorded, which is
    every federated account, and there is nothing to have invalidated.
    """
    if not stamp:
        return False
    return datetime.fromisoformat(stamp) >= session_started


class AuthService:
    """Orchestrates sign-in and hands out backend session cookies."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        # five collaborating singletons, injected explicitly for composition
        self,
        providers: dict[str, OAuthProvider],
        pending_store: PendingLoginStore,
        account_store: AccountStore,
        session_manager: SessionManager,
        signer: SessionSigner,
        *,
        pepper: bytes,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._providers = providers
        self._pending = pending_store
        self._accounts = account_store
        self._sessions = session_manager
        self._signer = signer
        self._pepper = pepper
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._throttle = LoginThrottle(self._clock)

    @property
    def requires_login(self) -> bool:
        """Always true. No configuration makes a gated route serve an anonymous caller."""
        return True

    @property
    def providers(self) -> list[str]:
        """The names of the configured OAuth providers, empty when there are none."""
        return list(self._providers)

    def login_with_password(self, username: str, password: str, *, client_ip: str) -> str:
        """Sign *username* in with *password*, start its session, and return the username.

        Raises LoginFailedError for every refusal and RateLimitedError when the backoff
        is still in force. *client_ip* is the caller's address, used only to throttle.
        """
        # Normalized once, up front, and used for the throttle as well as the store. Keying
        # the backoff on the raw username would hand an attacker a fresh allowance for
        # every spelling of the same account — abby, ABBY, " abby " — which defeats it
        # entirely.
        key = normalize_username(username)
        remaining = self._throttle.delay_for(key, client_ip)
        if remaining > 0:
            # Refused before the hash is touched. The throttle then applies to the
            # correct password too, or it would only slow an attacker's wrong guesses
            # while leaving them free to keep trying the right one.
            raise RateLimitedError(remaining)

        credentials = self._accounts.get_credentials(key)
        # The password is verified before the account is judged, including for a blocked
        # or deleted one, so a refusal costs the same everywhere and the form cannot be
        # used to learn which usernames exist or which are blocked. A missing account and
        # a NULL hash both verify against DUMMY_HASH to keep that cost.
        verified = verify_password(self._pepper, password, _stored_hash(credentials))
        if not verified or credentials is None or not _may_sign_in(credentials):
            self._throttle.record_failure(key, client_ip)
            raise LoginFailedError(_LOGIN_REFUSED)

        self._accounts.record_login(key)
        self._sessions.create(key)
        self._throttle.record_success(key, client_ip)
        return key

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        """Replace *username*'s password, having first proved *current_password*.

        Clears ``must_change_password``, since changing the password is what it asks for.
        Raises LoginFailedError, PasswordPolicyError or PasswordUnchangedError.
        """
        key = normalize_username(username)
        credentials = self._accounts.get_credentials(key)
        verified = verify_password(self._pepper, current_password, _stored_hash(credentials))
        if not verified or credentials is None or not _may_sign_in(credentials):
            raise LoginFailedError(_LOGIN_REFUSED)
        if new_password and verify_password(self._pepper, new_password, credentials["password_hash"]):
            raise PasswordUnchangedError("that is already your password")
        # The policy runs before the store is touched, so a rejected password leaves the
        # stored one in force and no stamp is written.
        new_hash = hash_password(self._pepper, new_password)
        self._accounts.set_password_hash(key, new_hash, must_change_password=False)

    def resolve_session(self, user_id: str) -> str | None:
        """Return *user_id* when its live session and stored credentials still agree.

        None when the session is gone, the account is blocked or deleted, or the
        credentials were changed after the session began. The last of those is what makes
        an admin CLI's block or reset take effect on a session it cannot reach.
        """
        session = self._sessions.get(user_id)
        if session is None:
            return None
        credentials = self._accounts.get_credentials(user_id)
        if credentials is None or not _may_sign_in(credentials):
            return None
        if _credentials_changed_since(credentials["credentials_changed_at"], session.created_at):
            return None
        return user_id

    def requires_password_change(self, user_id: str) -> bool:
        """Whether *user_id* signed in on a temporary password and must replace it."""
        credentials = self._accounts.get_credentials(user_id)
        return bool(credentials and credentials["must_change_password"])

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
        credentials = self._accounts.get_credentials(user_id)
        if credentials and not _may_sign_in(credentials):
            raise LoginFailedError(_LOGIN_REFUSED)
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
