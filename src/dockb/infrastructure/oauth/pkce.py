"""PKCE (RFC 7636) helpers for the Authorization Code flow."""

from __future__ import annotations

import base64
import hashlib
import secrets


def create_code_verifier() -> str:
    """Return a 64-character URL-safe random code verifier."""
    return secrets.token_urlsafe(48)


def s256_challenge(code_verifier: str) -> str:
    """Return the S256 PKCE ``code_challenge`` for *code_verifier*."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
