"""Tests for PKCE helpers."""

from __future__ import annotations

import re
import string

from dockb.infrastructure.oauth.pkce import create_code_verifier, s256_challenge

_URLSAFE = set(string.ascii_letters + string.digits + "-_")


def test_code_verifier_is_random_urlsafe_string() -> None:
    first = create_code_verifier()
    second = create_code_verifier()
    assert first != second
    assert len(first) >= 43
    assert all(char in _URLSAFE for char in first)


def test_s256_challenge_is_urlsafe_unpadded_base64() -> None:
    challenge = s256_challenge("a-code-verifier")
    assert re.fullmatch(r"[A-Za-z0-9_-]+", challenge)
    assert "=" not in challenge


def test_s256_challenge_matches_verifier_and_is_deterministic() -> None:
    verifier = create_code_verifier()
    assert s256_challenge(verifier) == s256_challenge(verifier)
    assert s256_challenge(verifier) != s256_challenge(verifier + "x")
