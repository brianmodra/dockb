"""Shared account identity, time, error, and encryptor helpers."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken


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
    username and SQLite compares TEXT case-sensitively.
    """
    return username.strip().lower()


def now_iso() -> str:
    """Return an ISO-8601 UTC timestamp of fixed width."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def constraint_error(exc: sqlite3.IntegrityError) -> AccountError:
    """Translate a UNIQUE violation into the account error naming the column."""
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


def reject_unknown_user(rowcount: int, username: str) -> None:
    """Report a mistyped username in the CLI rather than silently doing nothing."""
    if rowcount == 0:
        raise UnknownUserError(f"unknown user '{username}'")
