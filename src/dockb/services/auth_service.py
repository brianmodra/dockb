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

import hashlib
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp

from dockb.infrastructure.accounts.store import AccountStore, normalize_username
from dockb.infrastructure.email.service import EmailService, EmailUnavailableError
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
_CHALLENGE_TTL_SECONDS = 300
_EMAIL_OTP_TTL_SECONDS = 300
_RESET_TTL_SECONDS = 86400
_ENROLLMENT_TTL_SECONDS = 300


class InvalidTwoFactorError(Exception):
    """The supplied 2FA challenge or code was wrong, stale, or already used."""


class InvalidResetTokenError(Exception):
    """The supplied password-reset token was wrong, stale, or already used."""


@dataclass(frozen=True)
class PasswordLoginResult:
    """The immediate result of a password check, before any required second factor."""

    username: str
    challenge: str | None = None
    method: str | None = None

    @property
    def requires_two_factor(self) -> bool:
        """Whether a second factor must be completed before a session exists."""
        return self.challenge is not None


@dataclass(frozen=True)
class TwoFactorEnrollment:
    """What the editor needs in order to display an enrollment choice."""

    method: str
    secret: str | None = None
    provisioning_uri: str | None = None


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


class AuthService:  # pylint: disable=too-many-instance-attributes,too-many-public-methods
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
        email_service: EmailService | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._providers = providers
        self._pending = pending_store
        self._accounts = account_store
        self._sessions = session_manager
        self._signer = signer
        self._email = email_service
        self._pepper = pepper
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._throttle = LoginThrottle(self._clock)
        self._pending_enrollments: dict[str, tuple[str, str | None, datetime]] = {}
        self._enrollment_lock = threading.Lock()

    @property
    def requires_login(self) -> bool:
        """Always true. No configuration makes a gated route serve an anonymous caller."""
        return True

    @property
    def providers(self) -> list[str]:
        """The names of the configured OAuth providers, empty when there are none."""
        return list(self._providers)

    def login_with_password(self, username: str, password: str, *, client_ip: str) -> PasswordLoginResult:
        """Check *password* and either sign in or return a required second factor.

        Raises LoginFailedError for every refusal and RateLimitedError when the backoff
        is still in force. *client_ip* is the caller's address, used only to throttle.
        """
        key = normalize_username(username)
        remaining = self._throttle.delay_for(key, client_ip)
        if remaining > 0:
            raise RateLimitedError(remaining)

        credentials = self._accounts.get_credentials(key)
        verified = verify_password(self._pepper, password, _stored_hash(credentials))
        if not verified or credentials is None or not _may_sign_in(credentials):
            self._throttle.record_failure(key, client_ip)
            raise LoginFailedError(_LOGIN_REFUSED)

        self._throttle.record_success(key, client_ip)
        state = self._accounts.get_two_factor_state(key)
        method = state["method"] if state else None
        if method is None:
            self._accounts.record_login(key)
            self._sessions.create(key)
            return PasswordLoginResult(key)
        if method == "totp":
            return PasswordLoginResult(key, challenge=self._issue_login_challenge(key, method), method=method)
        if method == "email":
            self._send_email_code(key)
            return PasswordLoginResult(key, challenge=self._issue_login_challenge(key, method), method=method)
        raise InvalidTwoFactorError("unsupported two-factor method")

    def complete_two_factor_login(self, challenge: str, code: str) -> str:
        """Verify *code* for *challenge*, then start the pending session."""
        if not challenge or not code:
            raise InvalidTwoFactorError("invalid two-factor code")
        now = self._now()
        token_hash = self._hash("login-challenge", challenge)
        username = self._accounts.get_login_challenge(token_hash, now=now)
        if username is None:
            raise InvalidTwoFactorError("invalid two-factor challenge")

        state = self._accounts.get_two_factor_state(username)
        method = state["method"] if state else None
        if method == "totp":
            secret = state["totp_secret"] if state else None
            if not secret or not self._totp_matches(secret, code):
                raise InvalidTwoFactorError("invalid two-factor code")
        elif method == "email":
            if not self._accounts.verify_email_otp(username, code_hash=self._hash("email-otp", code.strip()), now=now):
                raise InvalidTwoFactorError("invalid two-factor code")
        else:
            raise InvalidTwoFactorError("no two-factor method configured")

        if self._accounts.consume_login_challenge(token_hash, now=now) != username:
            raise InvalidTwoFactorError("invalid two-factor challenge")
        self._accounts.record_login(username)
        self._sessions.create(username)
        return username

    def request_password_reset(self, email: str) -> None:
        """Mail a single-use reset link to the account owning *email*, if any."""
        user = self._accounts.get_user_by_email(email.strip().lower())
        if user is None:
            return
        token = secrets.token_urlsafe(32)
        self._require_email_service().send_password_reset(user["email"], token)
        self._accounts.issue_password_reset(
            user["username"],
            token_hash=self._hash("password-reset", token),
            expires_at=self._expiry(_RESET_TTL_SECONDS),
        )

    def reset_password(self, token: str, new_password: str) -> None:
        """Replace the password named by a valid reset *token* and cancel 2FA."""
        new_hash = hash_password(self._pepper, new_password)
        username = self._accounts.consume_password_reset(self._hash("password-reset", token), now=self._now())
        if username is None:
            raise InvalidResetTokenError("invalid password-reset token")
        self._accounts.set_password_hash(username, new_hash, must_change_password=False)
        self._accounts.clear_two_factor(username)

    def begin_two_factor_enrollment(self, username: str, method: str) -> TwoFactorEnrollment:
        """Start enrollment in TOTP or email OTP for the signed-in *username*."""
        if method not in {"totp", "email"}:
            raise ValueError(f"unsupported two-factor method: {method}")
        key = normalize_username(username)
        deadline = self._deadline(_ENROLLMENT_TTL_SECONDS)
        with self._enrollment_lock:
            self._discard_stale_enrollment(key)
            if method == "totp":
                secret = pyotp.random_base32()
                uri = pyotp.TOTP(secret).provisioning_uri(name=key, issuer_name="DockB")
                self._pending_enrollments[key] = (method, secret, deadline)
                return TwoFactorEnrollment(method=method, secret=secret, provisioning_uri=uri)
            self._send_email_code(key)
            self._pending_enrollments[key] = (method, None, deadline)
            return TwoFactorEnrollment(method=method)

    def confirm_two_factor_enrollment(self, username: str, method: str, code: str) -> None:
        """Enable a pending enrollment once its verification code checks out."""
        key = normalize_username(username)
        with self._enrollment_lock:
            pending = self._pending_enrollments.get(key)
            if pending is None or pending[0] != method or self._clock() >= pending[2]:
                raise InvalidTwoFactorError("no pending two-factor enrollment")
            secret = pending[1]
            if method == "totp":
                if not secret or not self._totp_matches(secret, code):
                    raise InvalidTwoFactorError("invalid two-factor code")
                self._accounts.set_two_factor(key, method="totp", totp_secret=secret)
            else:
                if not self._accounts.verify_email_otp(key, code_hash=self._hash("email-otp", code.strip()), now=self._now()):
                    raise InvalidTwoFactorError("invalid two-factor code")
                self._accounts.set_two_factor(key, method="email")
            self._pending_enrollments.pop(key, None)

    def two_factor_method(self, username: str) -> str | None:
        """Return the account's configured 2FA method, if it has one."""
        state = self._accounts.get_two_factor_state(normalize_username(username))
        return state["method"] if state else None

    def disable_two_factor(self, username: str) -> None:
        """Remove the account's 2FA method and every pending related credential."""
        key = normalize_username(username)
        with self._enrollment_lock:
            self._pending_enrollments.pop(key, None)
        self._accounts.clear_two_factor(key)

    def _issue_login_challenge(self, username: str, method: str) -> str:
        token = secrets.token_urlsafe(32)
        self._accounts.issue_login_challenge(
            username,
            token_hash=self._hash("login-challenge", token),
            method=method,
            expires_at=self._expiry(_CHALLENGE_TTL_SECONDS),
        )
        return token

    def _send_email_code(self, username: str) -> None:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._require_email_service().send_email_otp(self._account_email(username), code)
        self._accounts.issue_email_otp(
            username,
            code_hash=self._hash("email-otp", code),
            expires_at=self._expiry(_EMAIL_OTP_TTL_SECONDS),
        )

    def _require_email_service(self) -> EmailService:
        if self._email is None:
            raise EmailUnavailableError("email is not configured")
        return self._email

    def _account_email(self, username: str) -> str:
        user = self._accounts.get_user(username)
        email = user["email"] if user else None
        if not email or not email.strip():
            raise EmailUnavailableError("the account has no email address")
        return str(email).strip()

    @staticmethod
    def _totp_matches(secret: str, code: str) -> bool:
        try:
            return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _hash(domain: str, value: str) -> str:
        return hashlib.sha256(f"dockb-{domain}:{value}".encode()).hexdigest()

    def _now(self) -> str:
        return self._clock().isoformat()

    def _deadline(self, seconds: int) -> datetime:
        return self._clock() + timedelta(seconds=seconds)

    def _expiry(self, seconds: int) -> str:
        return self._deadline(seconds).isoformat()

    def _discard_stale_enrollment(self, username: str) -> None:
        pending = self._pending_enrollments.get(username)
        if pending is not None and self._clock() >= pending[2]:
            self._pending_enrollments.pop(username, None)

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

        A session refused here is also dropped, rather than merely not resolving. Refusing
        is a permanent state, not a temporary one — a stamp only moves forward, and a block
        or delete is not undone — so a context left behind could never serve a request
        again and would sit holding its job queue and doc cache for the life of the process.
        The block, delete and reset paths all depend on this, since the CLI cannot reach
        the server's sessions to evict them itself.
        """
        session = self._sessions.get(user_id)
        if session is None:
            return None
        credentials = self._accounts.get_credentials(user_id)
        if credentials is None or not _may_sign_in(credentials):
            self._sessions.remove(user_id)
            return None
        if _credentials_changed_since(credentials["credentials_changed_at"], session.created_at):
            self._sessions.remove(user_id)
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

    def get_user_by_id(self, user_id: str) -> dict[str, object] | None:
        """Return the stored profile for the internal id *user_id*, or None."""
        return self._accounts.get_user_by_id(user_id)

    def session_for(self, user_id: str) -> object | None:
        """Return the live SessionContext for *user_id*, possibly None (e.g. after restart)."""
        return self._sessions.get(user_id)

    def end_session(self, user_id: str) -> None:
        """Drop *user_id*'s server-side session, so its cookie stops resolving.

        The cookie itself is signed and will still verify — only the session behind
        it is gone — so the route also has to clear it in the browser. Dropping the
        session is what does the work: the cookie alone is not a session.
        """
        self._sessions.remove(user_id)

    def get_app_state(self, user_id: str) -> dict[str, object] | None:
        """Return the user's stored app-state row, or None."""
        return self._accounts.get_app_state(user_id)

    def set_app_state(self, user_id: str, state: dict[str, object]) -> None:
        """Upsert the user's app state as a whole."""
        self._accounts.set_app_state(user_id, state)

    def get_proofreading_language(self, user_id: str) -> str | None:
        """Return the proofreading language the user last chose, if any."""
        return self._accounts.get_proofreading_language(user_id)

    def set_proofreading_language(self, user_id: str, language: str) -> None:
        """Store the user's chosen proofreading language."""
        self._accounts.set_proofreading_language(user_id, language)

    @property
    def session_ttl_seconds(self) -> int:
        """How long a session cookie stays valid."""
        return self._signer.ttl_seconds
