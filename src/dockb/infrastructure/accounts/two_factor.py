"""Password recovery and two-factor state stored alongside accounts."""

from __future__ import annotations

import hmac
import sqlite3
from typing import Any

from .common import normalize_username, now_iso, reject_unknown_user

TWO_FACTOR_KEY_CONTEXT = "dockb-two-factor-totp"
MAX_EMAIL_OTP_ATTEMPTS = 5

TWO_FACTOR_MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN two_factor_method TEXT;
ALTER TABLE users ADD COLUMN totp_secret BLOB;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_challenges (
    token_hash  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    method      TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_otps (
    username    TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);
"""

TWO_FACTOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_challenges (
    token_hash  TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    method      TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_otps (
    username    TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (username) REFERENCES users (username) ON DELETE CASCADE
);
"""


def add_two_factor(connection: sqlite3.Connection) -> None:
    """Add the 2FA columns and recovery tables to an existing v4 database."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "two_factor_method" in columns:
        return
    connection.executescript(f"BEGIN;\n{TWO_FACTOR_MIGRATION_SQL}\nCOMMIT;")


class TwoFactorStoreMixin:
    """Recovery-token and 2FA accessors for AccountStore."""

    _totp_encryptor: Any

    def _connect(self) -> sqlite3.Connection:
        """Open a connection; implemented by AccountStore."""
        raise NotImplementedError

    def set_two_factor(self, username: str, *, method: str | None, totp_secret: str | None = None) -> None:
        """Set the user's single 2FA method, encrypting any TOTP secret."""
        secret = totp_secret if method == "totp" else None
        ciphertext = self._totp_encryptor.encrypt(secret) if secret else None
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE users SET two_factor_method = ?, totp_secret = ? WHERE username = ?",
                (method, ciphertext, normalize_username(username)),
            )
            reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def get_two_factor_state(self, username: str) -> dict[str, Any] | None:
        """Return the user's 2FA method and decrypted TOTP secret, if present."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT two_factor_method, totp_secret FROM users WHERE username = ?",
                (normalize_username(username),),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        ciphertext = row["totp_secret"]
        secret = self._totp_encryptor.try_decrypt(ciphertext) if isinstance(ciphertext, bytes) else None
        return {"method": row["two_factor_method"], "totp_secret": secret}

    def clear_two_factor(self, username: str) -> None:
        """Remove all 2FA state and pending recovery/challenge state for a user."""
        key = normalize_username(username)
        stamp = now_iso()
        connection = self._connect()
        try:
            connection.execute("DELETE FROM password_reset_tokens WHERE username = ?", (key,))
            connection.execute("DELETE FROM login_challenges WHERE username = ?", (key,))
            connection.execute("DELETE FROM email_otps WHERE username = ?", (key,))
            cursor = connection.execute(
                """
                UPDATE users
                   SET two_factor_method = NULL, totp_secret = NULL, credentials_changed_at = ?
                 WHERE username = ?
                """,
                (stamp, key),
            )
            reject_unknown_user(cursor.rowcount, username)
            connection.commit()
        finally:
            connection.close()

    def issue_password_reset(self, username: str, *, token_hash: str, expires_at: str) -> None:
        """Store a hashed single-use password-reset token."""
        key = normalize_username(username)
        connection = self._connect()
        try:
            connection.execute("DELETE FROM password_reset_tokens WHERE username = ?", (key,))
            connection.execute(
                """
                INSERT INTO password_reset_tokens (token_hash, username, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, key, expires_at, now_iso()),
            )
            connection.commit()
        finally:
            connection.close()

    def consume_password_reset(self, token_hash: str, *, now: str) -> str | None:
        """Return the username for a valid reset token, consuming it once."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT username, expires_at FROM password_reset_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            valid = now < row["expires_at"]
            connection.execute("DELETE FROM password_reset_tokens WHERE token_hash = ?", (token_hash,))
            connection.commit()
            return str(row["username"]) if valid else None
        finally:
            connection.close()

    def issue_login_challenge(self, username: str, *, token_hash: str, method: str, expires_at: str) -> None:
        """Store a hashed single-use 2FA login challenge."""
        key = normalize_username(username)
        connection = self._connect()
        try:
            connection.execute("DELETE FROM login_challenges WHERE username = ?", (key,))
            connection.execute(
                """
                INSERT INTO login_challenges (token_hash, username, method, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash, key, method, expires_at, now_iso()),
            )
            connection.commit()
        finally:
            connection.close()

    def get_login_challenge(self, token_hash: str, *, now: str) -> str | None:
        """Return the username for a valid 2FA challenge without consuming it."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT username, expires_at FROM login_challenges WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or now >= row["expires_at"]:
            return None
        return str(row["username"])

    def consume_login_challenge(self, token_hash: str, *, now: str) -> str | None:
        """Return the username for a valid 2FA challenge, consuming it once."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT username, expires_at FROM login_challenges WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            valid = now < row["expires_at"]
            connection.execute("DELETE FROM login_challenges WHERE token_hash = ?", (token_hash,))
            connection.commit()
            return str(row["username"]) if valid else None
        finally:
            connection.close()

    def issue_email_otp(self, username: str, *, code_hash: str, expires_at: str) -> None:
        """Replace the user's hashed email OTP and reset its attempt count."""
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO email_otps (username, code_hash, expires_at, attempts, created_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT (username) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    expires_at = excluded.expires_at,
                    attempts = 0,
                    created_at = excluded.created_at
                """,
                (normalize_username(username), code_hash, expires_at, now_iso()),
            )
            connection.commit()
        finally:
            connection.close()

    def verify_email_otp(self, username: str, *, code_hash: str, now: str) -> bool:
        """Consume a matching, unexpired email OTP within the attempt limit."""
        key = normalize_username(username)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT code_hash, expires_at, attempts FROM email_otps WHERE username = ?",
                (key,),
            ).fetchone()
            if row is None:
                return False
            if now >= row["expires_at"]:
                connection.execute("DELETE FROM email_otps WHERE username = ?", (key,))
                connection.commit()
                return False
            if not hmac.compare_digest(str(row["code_hash"]), code_hash):
                attempts = int(row["attempts"]) + 1
                if attempts >= MAX_EMAIL_OTP_ATTEMPTS:
                    connection.execute("DELETE FROM email_otps WHERE username = ?", (key,))
                else:
                    connection.execute("UPDATE email_otps SET attempts = ? WHERE username = ?", (attempts, key))
                connection.commit()
                return False
            connection.execute("DELETE FROM email_otps WHERE username = ?", (key,))
            connection.commit()
            return True
        finally:
            connection.close()
