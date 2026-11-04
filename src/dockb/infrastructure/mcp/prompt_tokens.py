"""Per-prompt MCP bearer tokens — mint and verify over an in-memory live-token map.

The token is ``expiry.prompt_id.mac(expiry + "." + prompt_id)`` where ``mac`` is
HMAC-SHA256 under the secret held in that expiry's map entry. There is no
credential store: entries are pruned when their expiry passes, and a process
restart invalidates everything. See ``README_mcp_auth.md`` §3 and this package's
``README.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time

logger = logging.getLogger(__name__)

_TTL_ENV_VAR = "DOCKB_MCP_TOKEN_TTL_SECONDS"
_DEFAULT_TTL_SECONDS = 300.0
_MAC_HEX_DIGITS = 64


def _mac(secret: bytes, signed: str) -> str:
    return hmac.new(secret, signed.encode("utf-8"), hashlib.sha256).hexdigest()


def _log_safe(value: str) -> str:
    """Collapse control characters so a caller-supplied id cannot forge a log line."""
    return "".join(character if character.isprintable() else " " for character in value)


class PromptTokenIssuer:
    """Mints and verifies per-prompt bearer tokens for the MCP endpoint."""

    def __init__(self, ttl_seconds: float | None = None) -> None:
        if ttl_seconds is None:
            ttl_seconds = float(os.environ.get(_TTL_ENV_VAR, str(_DEFAULT_TTL_SECONDS)))
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, dict[str, tuple[bytes, str]]] = {}

    @property
    def ttl_seconds(self) -> float:
        """The configured token lifetime in seconds."""
        return self._ttl_seconds

    def mint(self, prompt_id: str, account_id: str) -> str:
        """Mint a token for *prompt_id* bound to *account_id*, valid until now + the TTL.

        The account is the tool-side subject: everything an MCP tool reads is
        scoped to it, exactly as an editor session's reads are scoped to the
        signed-in account. A token without one could read nobody's books, so
        minting refuses to make one.
        """
        if not account_id or not account_id.strip():
            raise ValueError("an MCP token needs the account it is minted for")
        now = time.time()
        self._prune(now)
        expiry = str(int((now + self._ttl_seconds) * 1_000_000))
        secret = secrets.token_bytes(32)
        self._entries.setdefault(expiry, {})[prompt_id] = (secret, account_id.strip())
        return f"{expiry}.{prompt_id}.{_mac(secret, f'{expiry}.{prompt_id}')}"

    def verify(self, token: str) -> str | None:
        """Return the prompt identity a valid token belongs to, else None."""
        reason = self._check(token)
        prompt_id = self._prompt_id_of(token)
        outcome = "accepted" if reason is None else f"rejected ({reason})"
        logger.info("MCP token %s for prompt %s", outcome, _log_safe(prompt_id))
        return None if reason is not None else prompt_id

    def _check(self, token: str) -> str | None:
        """Return the reason *token* is invalid, or None if it is valid."""
        fields = self._parse(token)
        if fields is None:
            return "malformed"
        expiry, prompt_id, presented = fields
        if not expiry.isdigit() or len(presented) != _MAC_HEX_DIGITS:
            return "malformed"
        if int(expiry) <= time.time() * 1_000_000:
            return "expired"
        entry = self._entries.get(expiry, {}).get(prompt_id)
        if entry is None:
            return "no live entry"
        secret = entry[0]
        if not hmac.compare_digest(_mac(secret, f"{expiry}.{prompt_id}"), presented):
            return "mac mismatch"
        return None

    @staticmethod
    def _parse(token: str) -> tuple[str, str, str] | None:
        """Split *token* into expiry, prompt id and MAC — expiry and MAC are dot-free."""
        first, dot, rest = token.partition(".")
        prompt_id, last_dot, mac = rest.rpartition(".")
        if not dot or not last_dot or not prompt_id:
            return None
        return first, prompt_id, mac

    def account_of(self, token: str) -> str | None:
        """Return the account *token* was minted for, or None when it is invalid.

        Verified with the same check ``verify`` runs, so an answer only ever
        comes from a token that would pass the bearer gate.
        """
        if self._check(token) is not None:
            return None
        fields = self._parse(token)
        if fields is None:
            return None
        entry = self._entries.get(fields[0], {}).get(fields[1])
        return str(entry[1]) if entry is not None else None

    @classmethod
    def _prompt_id_of(cls, token: str) -> str:
        fields = cls._parse(token)
        return fields[1] if fields is not None else "<malformed>"

    def _prune(self, now: float) -> None:
        """Drop entries whose expiry has passed so abandoned tokens do not accumulate."""
        now_micros = now * 1_000_000
        for expiry in [key for key in self._entries if int(key) <= now_micros]:
            del self._entries[expiry]
