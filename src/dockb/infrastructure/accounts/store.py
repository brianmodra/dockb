"""Server-owned account data, tokens, and per-user app state in SQLite.

The relational store lives as a single ``dockb_app.db`` file beside the
backend's owned markdown tree (``DOCKB_CHAPTERS_DIR``). Accounts are not
part of the document graph (Neo4j), so they live in their own SQLite store.

User identity is the unique ``users.username`` column everywhere: sessions,
cookies, and app state carry the username (the OS user in local mode, the
OAuth profile username otherwise).

See ``README_auth.md``.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_DB_FILENAME = "dockb_app.db"

logger = logging.getLogger(__name__)


class AccountError(Exception):
    """Base class for account-store failures the caller is expected to handle."""


class UnknownUserError(AccountError):
    """No account exists for the given username."""


class UsernameTakenError(AccountError):
    """The username is already in use by another account."""


class EmailTakenError(AccountError):
    """The email address is already in use by another account."""


def normalize_username(username: str) -> str:
    """Return *username* in the one form the store keys and compares it by.

    Stored lowercased with surrounding whitespace stripped, because identity is the
    username (``README_auth.md`` §3) and SQLite compares TEXT case-sensitively, so
    ``Brian`` and ``brian`` would otherwise be two accounts. Normalizing here rather
    than at the call sites means no accessor can bypass it.
    """
    return username.strip().lower()


def _now() -> str:
    """Return an ISO-8601 UTC timestamp of fixed width, in UTC.

    Sub-second because ``credentials_changed_at`` is compared against a session's
    creation time to invalidate sessions the CLI cannot reach, and ``CURRENT_TIMESTAMP``
    resolves only to the second — a session created in the same second as a password
    reset would compare equal and survive it.

    ``timespec`` is explicit because ``isoformat()`` drops the microseconds when they
    happen to be zero, which yields two different widths for the same field. The
    comparison is a plain string comparison, so the widths have to match: they sort in
    the right order today only by accident, because '+' sorts before '.'.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _constraint_error(exc: sqlite3.IntegrityError) -> AccountError:
    """Translate a UNIQUE violation into the account error naming the column.

    The CLI reports which of the two collided, so that a user can be told their address
    is spoken for without inspecting a SQLite message.
    """
    message = str(exc)
    if "users.username" in message:
        return UsernameTakenError("that username is already in use")
    if "users.email" in message:
        return EmailTakenError("that email address is already in use")
    return AccountError(message)


class TokenEncryptor:
    """Encrypts and decrypts refresh tokens at rest with a Fernet key."""

    def __init__(self, secret: str) -> None:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def encrypt(self, token: str) -> bytes:
        """Encrypt a plaintext token."""
        return self._fernet.encrypt(token.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a token ciphertext, raising InvalidToken on failure."""
        return self._fernet.decrypt(ciphertext).decode("utf-8")

    def try_decrypt(self, ciphertext: bytes) -> str | None:
        """Return the decrypted token, or None if the key does not match."""
        try:
            return self.decrypt(ciphertext)
        except InvalidToken:
            return None


def _reject_unknown_user(rowcount: int, username: str) -> None:
    """Report a mistyped username in the CLI rather than silently doing nothing."""
    if rowcount == 0:
        raise UnknownUserError(f"unknown user '{username}'")


class AccountStore:
    """SQLite store for users, oauth accounts, and per-user app state.

    Identities are usernames. ``users`` keeps an internal numeric-style UUID
    id only for the ``oauth_accounts`` foreign key; every public accessor and
    the ``app_state`` table are keyed by ``users.username``.
    """

    def __init__(self, base_dir: Path, secret: str) -> None:
        self._db_path = Path(base_dir) / _DB_FILENAME
        self._encryptor = TokenEncryptor(secret)

    @classmethod
    def from_env(cls) -> AccountStore:
        """Build a store rooted at ``DOCKB_CHAPTERS_DIR`` with ``DOCKB_SECRET_KEY``."""
        base = os.environ.get("DOCKB_CHAPTERS_DIR")
        if not base:
            raise ValueError("DOCKB_CHAPTERS_DIR must be set to the markdown tree base directory")
        secret = os.environ.get("DOCKB_SECRET_KEY")
        if not secret:
            raise ValueError("DOCKB_SECRET_KEY must be set for token encryption")
        return cls(Path(base), secret)

    # ------------------------------------------------------------------ wiring

    def _connect(self) -> sqlite3.Connection:
        """Open a connection, bringing the schema up to the current version.

        A database created here already has the full current shape, so it is stamped
        at the current version rather than migrated. An existing database is stepped
        through the migrations below, because ``_SCHEMA`` alone is made entirely of
        ``CREATE TABLE IF NOT EXISTS`` and would silently leave new columns absent.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        pre_existing = self._table_exists(connection, "users")
        connection.executescript(_SCHEMA)
        try:
            if pre_existing:
                self._apply_migrations(connection)
            else:
                # Nothing to reconcile on a database that did not exist, so the unique
                # email index can be created straight away. An existing one goes through
                # the migration below, which has to resolve duplicates before the index
                # can hold.
                connection.executescript(_EMAIL_UNIQUE_INDEX)
                connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.commit()
        except sqlite3.Error:
            # _connect has not returned yet, so no caller can close this for us.
            connection.close()
            raise
        return connection

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
        """Return whether a table named *name* is present."""
        row = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
        return row is not None

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        """Step an existing database up to ``_SCHEMA_VERSION``.

        ``PRAGMA user_version`` is an integer held in the file header, so it records
        how far this database has been taken without a second bookkeeping table. Each
        step stamps its version only after it succeeds; see ``_add_password_credentials``
        for why that ordering matters.
        """
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        for version, apply_step in _MIGRATIONS:
            if version <= current:
                continue
            apply_step(connection)
            connection.execute(f"PRAGMA user_version = {version}")

    # ------------------------------------------------------------------ users

    def get_user(self, username: str) -> dict[str, Any] | None:
        """Return the user row with *username*, or None."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (normalize_username(username),)).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def get_user_by_provider_account(self, provider: str, provider_account_id: str) -> dict[str, Any] | None:
        """Return the user linked to a provider account, or None."""
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT u.* FROM users u
                JOIN oauth_accounts oa ON oa.user_id = u.id
                WHERE oa.provider = ? AND oa.provider_account_id = ?
                """,
                (provider, provider_account_id),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def upsert_provider_user(  # pylint: disable=too-many-arguments
        # token/expires_at are keyword-only and keep the login call site readable
        self,
        provider: str,
        provider_account_id: str,
        *,
        username: str,
        email: str | None,
        display_name: str,
        avatar_url: str | None,
        token: str | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Return the username for a provider account, creating or refreshing the profile.

        First login creates a ``users`` row and links it to the provider account;
        later logins refresh profile fields (username included) and the encrypted
        token in place, with no account merging across providers.

        An address already held by a *different* account is refused before anything is
        written, so a failed login leaves neither a ``users`` row nor a provider link.
        """
        key = normalize_username(username)
        user = self.get_user_by_provider_account(provider, provider_account_id)
        ciphertext = self._encryptor.encrypt(token) if token is not None else None
        connection = self._connect()
        try:
            user_id = self._write_provider_profile(
                connection,
                username=key,
                email=email or None,
                display_name=display_name,
                avatar_url=avatar_url,
                user=user,
            )
            connection.execute(
                """
                INSERT INTO oauth_accounts (provider, provider_account_id, user_id, token, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (provider, provider_account_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    token = excluded.token,
                    expires_at = excluded.expires_at
                """,
                (provider, provider_account_id, user_id, ciphertext, expires_at),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise _constraint_error(exc) from exc
        finally:
            connection.close()
        return key

    def _write_provider_profile(  # pylint: disable=too-many-arguments
        # the profile fields are the users columns, kept together so the insert and the
        # update below read as the two halves of one upsert
        self,
        connection: sqlite3.Connection,
        *,
        username: str,
        email: str | None,
        display_name: str,
        avatar_url: str | None,
        user: dict[str, Any] | None,
    ) -> str:
        """Create or refresh the ``users`` row behind a provider login, returning its id.

        *user* is the row already linked to this provider account, or None on a first
        login. An address held by a different account is refused here, before the
        statement runs, so a failed login leaves neither a ``users`` row nor a link.
        """
        if user is None:
            self._require_email_free(connection, email, user_id=None)
            user_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO users (id, username, email, display_name, avatar_url) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, email, display_name, avatar_url),
            )
            return user_id
        existing_id: str = user["id"]
        self._require_email_free(connection, email, user_id=existing_id)
        connection.execute(
            "UPDATE users SET username = ?, email = ?, display_name = ?, avatar_url = ? WHERE id = ?",
            (username, email, display_name, avatar_url, existing_id),
        )
        return existing_id

    @staticmethod
    def _require_email_free(connection: sqlite3.Connection, email: str | None, *, user_id: str | None) -> None:
        """Raise EmailTakenError when *email* belongs to an account other than *user_id*.

        Checked rather than left to the constraint so the refusal happens before the
        surrounding statement runs. A NULL address is free, since NULL does not collide.
        """
        if email is None:
            return
        if user_id is None:
            taken = connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        else:
            taken = connection.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if taken is not None:
            raise EmailTakenError("that email address is already in use")

    # ------------------------------------------------- credentials and state

    def create_user(  # pylint: disable=too-many-arguments
        # the keyword-only arguments are the users columns a caller may set, and keeping
        # them named is what lets the admin CLI read as a sentence
        self,
        username: str,
        *,
        email: str | None,
        display_name: str,
        avatar_url: str | None = None,
        password_hash: str | None = None,
        must_change_password: bool = False,
    ) -> str:
        """Insert a new user row and return its normalized username.

        Raises UsernameTakenError or EmailTakenError rather than an IntegrityError, so
        the CLI can say which of the two collided. *email* of None is stored as NULL
        and not '', because a unique constraint does not collide two NULLs.
        """
        key = normalize_username(username)
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO users (
                    id, username, email, display_name, avatar_url,
                    password_hash, must_change_password
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    key,
                    email or None,
                    display_name,
                    avatar_url,
                    password_hash,
                    int(must_change_password),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise _constraint_error(exc) from exc
        finally:
            connection.close()
        return key

    def get_credentials(self, username: str) -> dict[str, Any] | None:
        """Return the account's sign-in state for *username*, or None when absent.

        The row a login needs: the password hash (None means this account cannot sign
        in with a password), must_change_password, blocked_at, deleted_at, and
        credentials_changed_at. Never returns the OAuth token.
        """
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT username, password_hash, must_change_password, blocked_at,
                       deleted_at, credentials_changed_at
                FROM users WHERE username = ?
                """,
                (normalize_username(username),),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def set_password_hash(
        self,
        username: str,
        password_hash: str | None,
        *,
        must_change_password: bool = False,
    ) -> None:
        """Store *password_hash* on *username* and stamp ``credentials_changed_at``.

        The stamp is what invalidates sessions the CLI cannot reach, since it runs in
        another process from the server's in-memory SessionManager.
        """
        stamp = _now()
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET password_hash = ?, must_change_password = ?, credentials_changed_at = ? WHERE username = ?",
                (password_hash, int(must_change_password), stamp, normalize_username(username)),
            )
            _reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def record_login(self, username: str) -> None:
        """Stamp ``last_login_at`` on *username* after a successful sign-in.

        Distinct from ``credentials_changed_at``, which is about invalidating sessions
        rather than recording that someone arrived.
        """
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET last_login_at = ? WHERE username = ?",
                (_now(), normalize_username(username)),
            )
            _reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def block_user(self, username: str) -> None:
        """Refuse logins for *username* and stamp ``credentials_changed_at``."""
        stamp = _now()
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET blocked_at = ?, credentials_changed_at = ? WHERE username = ?",
                (stamp, stamp, normalize_username(username)),
            )
            _reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def unblock_user(self, username: str) -> None:
        """Clear ``blocked_at`` for *username*, leaving ``credentials_changed_at``.

        Unblocking is not a credential change and must not invalidate anything: there are
        no live sessions to invalidate, since blocking already removed them.
        """
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET blocked_at = NULL WHERE username = ?",
                (normalize_username(username),),
            )
            _reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def soft_delete_user(self, username: str) -> None:
        """Stamp ``deleted_at`` for *username* and stamp ``credentials_changed_at``.

        Soft, so the row, its app state and its OAuth links survive and the manuscripts
        it wrote stay attributable. The username therefore stays taken.
        """
        stamp = _now()
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET deleted_at = ?, credentials_changed_at = ? WHERE username = ?",
                (stamp, stamp, normalize_username(username)),
            )
            _reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def list_users(self) -> list[dict[str, Any]]:
        """Return every account, oldest first, without password hashes.

        Excludes the hash and the id: this feeds the CLI's ``users list``, and a listing
        has no use for either.
        """
        connection = self._connect()
        try:
            rows = connection.execute("""
                SELECT username, email, display_name, avatar_url, must_change_password,
                       blocked_at, deleted_at, last_login_at, created_at
                FROM users ORDER BY created_at, username
                """).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    # ----------------------------------------------------------- oauth links

    def link_provider_account(  # pylint: disable=too-many-arguments
        # token/expiry are keyword-only and keep the call sites readable
        self,
        username: str,
        provider: str,
        provider_account_id: str,
        *,
        token: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        """Record *provider_account_id* on *username*, storing the token encrypted."""
        user = self.get_user(username)
        if user is None:
            raise ValueError(f"unknown user '{username}'")
        ciphertext = self._encryptor.encrypt(token) if token is not None else None
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO oauth_accounts (provider, provider_account_id, user_id, token, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (provider, provider_account_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    token = excluded.token,
                    expires_at = excluded.expires_at
                """,
                (provider, provider_account_id, user["id"], ciphertext, expires_at),
            )
            connection.commit()
        finally:
            connection.close()

    def get_provider_account(self, provider: str, provider_account_id: str) -> dict[str, Any] | None:
        """Return the provider account with its token decrypted, or None."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM oauth_accounts WHERE provider = ? AND provider_account_id = ?",
                (provider, provider_account_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        attrs = dict(row)
        token_ciphertext = attrs.pop("token", None)
        attrs["token"] = self._encryptor.decrypt(token_ciphertext) if isinstance(token_ciphertext, bytes) else None
        return attrs

    # ------------------------------------------------------------- app state

    def get_app_state(self, username: str) -> dict[str, Any] | None:
        """Return the username's app-state row, or None."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM app_state WHERE username = ?", (username,)).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def set_app_state(self, username: str, state: dict[str, Any]) -> None:
        """Replace the per-user app state, inserting when absent."""
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO app_state (username, last_document_id, panel_widths, edit_mode, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (username) DO UPDATE SET
                    last_document_id = excluded.last_document_id,
                    panel_widths = excluded.panel_widths,
                    edit_mode = excluded.edit_mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    username,
                    state.get("last_document_id"),
                    state.get("panel_widths"),
                    state.get("edit_mode"),
                ),
            )
            connection.commit()
        finally:
            connection.close()


_SCHEMA_VERSION = 2

# Created by name rather than as an inline UNIQUE on the column, so a fresh database and
# a migrated one hold it under the same name. SQLite cannot add a constraint with ALTER
# TABLE, which is why this is a statement rather than part of the users column list, and
# why it cannot live in _SCHEMA either: _SCHEMA runs before the migration below, and this
# constraint would then be attempted before the duplicate addresses it refuses are gone.
_EMAIL_UNIQUE_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email);"

# An existing database predates every column below and predates the unique email
# index, and it may already hold the duplicates that index refuses: a password account
# wrote an empty string rather than NULL, and a provider may have reported the same
# address twice. The duplicates are resolved first or creating the index fails and the
# backend will not start. The earliest row keeps the address and the rest are nulled,
# which loses an unverified address the CLI can re-supply.
_PASSWORD_CREDENTIALS_MIGRATION = """
UPDATE users SET email = NULL WHERE email IS NOT NULL AND TRIM(email) = '';

UPDATE users SET email = NULL
 WHERE email IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM users AS earlier
        WHERE earlier.email = users.email AND earlier.rowid < users.rowid
   );

ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN blocked_at TEXT;
ALTER TABLE users ADD COLUMN last_login_at TEXT;
ALTER TABLE users ADD COLUMN credentials_changed_at TEXT;
ALTER TABLE users ADD COLUMN deleted_at TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (email);
"""


def _warn_about_discarded_emails(connection: sqlite3.Connection) -> None:
    """Log every account whose address the migration below is about to clear.

    Both of the migration's ``UPDATE`` statements silently delete an unverified address,
    and an operator has no other way to learn which ones were lost, so each affected
    account is named. The address itself is not logged: the username is what an operator
    needs in order to re-supply it through the CLI.
    """
    rows = connection.execute("""
        SELECT username FROM users
         WHERE email IS NOT NULL
           AND (
               TRIM(email) = ''
               OR EXISTS (
                   SELECT 1 FROM users AS earlier
                    WHERE earlier.email = users.email AND earlier.rowid < users.rowid
               )
           )
         ORDER BY username
        """).fetchall()
    for row in rows:
        logger.warning(
            "cleared the stored email address of user %r to make email unique, because it was "
            "blank or already held by an earlier user; re-supply it with the users CLI if it is wanted",
            row["username"],
        )


def _add_password_credentials(connection: sqlite3.Connection) -> None:
    """Add the credential, blocking and deletion columns, and the unique email index.

    ``executescript`` issues an implicit COMMIT before it runs, so the transaction has to
    be part of the script rather than opened by the caller. The caller stamps the version
    only once this returns, which keeps a step that fails halfway — an ``ALTER TABLE``
    before the ``CREATE UNIQUE INDEX`` — from leaving the file at the old version where
    the retry would fail on a duplicate column instead of finishing the job.
    """
    _warn_about_discarded_emails(connection)
    connection.executescript(f"BEGIN;\n{_PASSWORD_CREDENTIALS_MIGRATION}\nCOMMIT;")


_MIGRATIONS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    # Version 1 is the original three-table shape: what an existing database already
    # has, and what _SCHEMA below still creates for a new one. It does nothing.
    (1, lambda _connection: None),
    (2, _add_password_credentials),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                      TEXT PRIMARY KEY,
    username                TEXT NOT NULL UNIQUE,
    email                   TEXT,
    display_name            TEXT,
    avatar_url              TEXT,
    password_hash           TEXT,
    must_change_password    INTEGER NOT NULL DEFAULT 0,
    blocked_at              TEXT,
    last_login_at           TEXT,
    credentials_changed_at  TEXT,
    deleted_at              TEXT,
    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oauth_accounts (
    provider             TEXT,
    provider_account_id  TEXT,
    user_id              TEXT NOT NULL,
    token                BLOB,
    expires_at           TEXT,
    PRIMARY KEY (provider, provider_account_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_state (
    username           TEXT PRIMARY KEY,
    last_document_id   TEXT,
    panel_widths       TEXT,
    edit_mode          TEXT,
    updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);
"""
