"""Tests for SessionSigner — signed, time-limited session cookie tokens."""

from __future__ import annotations

from dockb.infrastructure.session.session_cookie import SessionSigner

_SECRET = "super-secret"
_OTHER = "another-secret"


def test_sign_verify_round_trip() -> None:
    signer = SessionSigner(_SECRET)
    token = signer.sign("user-1")
    assert signer.verify(token) == "user-1"


def test_verify_tampered_token_returns_none() -> None:
    token = SessionSigner(_SECRET).sign("user-1")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert SessionSigner(_SECRET).verify(tampered) is None


def test_verify_token_from_other_secret_returns_none() -> None:
    token = SessionSigner(_SECRET).sign("user-1")
    assert SessionSigner(_OTHER).verify(token) is None


def test_verify_token_does_not_leak_user_when_expired() -> None:
    signer = SessionSigner(_SECRET, ttl_hours=0)
    token = signer.sign("user-1")
    assert signer.verify(token) is None


def test_ttl_seconds_from_hours() -> None:
    assert SessionSigner(_SECRET, ttl_hours=48).ttl_seconds == 48 * 3600
    assert SessionSigner(_SECRET, ttl_hours=2).ttl_seconds == 7200


def test_tokens_are_unique() -> None:
    signer = SessionSigner(_SECRET)
    assert signer.sign("user-1") != signer.sign("user-1")
