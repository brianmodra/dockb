"""Server-owned account data, tokens, and per-user app state in SQLite.

The relational store lives as a single ``dockb_app.db`` file beside the
backend's owned markdown tree (``DOCKB_CHAPTERS_DIR``). Accounts are not
part of the document graph (Neo4j), so they live in their own SQLite store.

See ``README_auth.md``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

_DB_FILENAME = "dockb_app.db"


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


class AccountStore:
    """SQLite store for users, oauth accounts, and per-user app state."""

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
        """Open a connection, ensuring the schema exists."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        return connection

    # ------------------------------------------------------------------ users

    def create_user(self, email: str, display_name: str, avatar_url: str) -> str:
        """Insert a new user row and return its id."""
        user_id = str(uuid.uuid4())
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO users (id, email, display_name, avatar_url) VALUES (?, ?, ?, ?)",
                (user_id, email, display_name, avatar_url),
            )
            connection.commit()
        finally:
            connection.close()
        return user_id

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Return the user row with *user_id*, or None."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
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

    # ----------------------------------------------------------- oauth links

    def link_provider_account(  # pylint: disable=too-many-arguments
        # token/expiry are keyword-only and keep the call sites readable
        self,
        user_id: str,
        provider: str,
        provider_account_id: str,
        *,
        token: str | None = None,
        expires_at: str | None = None,
    ) -> None:
        """Record *provider_account_id* on *user_id*, storing the token encrypted."""
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
                (provider, provider_account_id, user_id, ciphertext, expires_at),
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

    def get_app_state(self, user_id: str) -> dict[str, Any] | None:
        """Return the user's app-state row, or None."""
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM app_state WHERE user_id = ?", (user_id,)).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def set_app_state(self, user_id: str, state: dict[str, Any]) -> None:
        """Replace the per-user app state, inserting when absent."""
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO app_state (user_id, last_document_id, panel_widths, edit_mode, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    last_document_id = excluded.last_document_id,
                    panel_widths = excluded.panel_widths,
                    edit_mode = excluded.edit_mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    state.get("last_document_id"),
                    state.get("panel_widths"),
                    state.get("edit_mode"),
                ),
            )
            connection.commit()
        finally:
            connection.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT,
    display_name  TEXT,
    avatar_url    TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    user_id            TEXT PRIMARY KEY,
    last_document_id   TEXT,
    panel_widths       TEXT,
    edit_mode          TEXT,
    updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
"""
