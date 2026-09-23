"""Tests for the Google and GitHub providers (consent URL, code exchange, profile)."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

import httpx
import pytest

from dockb.infrastructure.oauth.pkce import s256_challenge
from dockb.infrastructure.oauth.provider import OAuthProviderError
from dockb.infrastructure.oauth.providers import GitHubProvider, GoogleProvider

_PORT = 8123
_VERIFIER = "fevEbERzorb1CgPfqi7LkMf3QZQNK_HDvTAISlzet537_LuSURHwGsy-0QbLLnW1"
_STATE = "abc123state"


def _mock_google(payload):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    return GoogleProvider("gid", "gsecret", _PORT, httpx.Client(transport=transport))


def _mock_github(handler):
    transport = httpx.MockTransport(handler)
    return GitHubProvider("ghid", "ghsecret", _PORT, httpx.Client(transport=transport))


# ---------------------------------------------------------- authorization url


@pytest.mark.parametrize("provider", [GoogleProvider("gid", "gs", _PORT), GitHubProvider("gid", "gs", _PORT)])
def test_authorization_url_carries_common_oauth_params(provider) -> None:
    url = provider.authorization_url(_STATE, _VERIFIER)
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    assert params["client_id"] == [provider.client_id]
    assert params["redirect_uri"] == [f"http://localhost:{_PORT}/callback"]
    assert params["response_type"] == ["code"]
    assert params["state"] == [_STATE]
    assert params["code_challenge"] == [s256_challenge(_VERIFIER)]
    assert params["code_challenge_method"] == ["S256"]


def test_google_authorization_url_adds_offline_access() -> None:
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(GoogleProvider("gid", "gs", _PORT).authorization_url(_STATE, _VERIFIER)).query)
    assert params["access_type"] == ["offline"]
    assert params["scope"] == ["openid email profile"]


def test_github_authorization_url_scopes() -> None:
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(GitHubProvider("gid", "gs", _PORT).authorization_url(_STATE, _VERIFIER)).query)
    assert params["scope"] == ["read:user user:email"]


# -------------------------------------------------------------- code exchange


def test_google_exchange_returns_tokens_and_expiry() -> None:
    provider = _mock_google({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3599})
    result = provider.exchange_code("code-1", _VERIFIER)
    assert result.access_token == "at-1"
    assert result.refresh_token == "rt-1"
    assert result.expires_at is not None
    now = datetime.now(timezone.utc)
    assert result.expires_at > now
    assert (result.expires_at - now).total_seconds() < 3600 + 10


def test_github_exchange_without_refresh_token() -> None:
    provider = _mock_github(lambda request: httpx.Response(200, json={"access_token": "at-1"}))
    result = provider.exchange_code("code-1", _VERIFIER)
    assert result.access_token == "at-1"
    assert result.refresh_token is None


def test_exchange_sends_code_verifier_and_secret() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(urllib.parse.parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "at"})

    _mock_github(handler).exchange_code("code-9", _VERIFIER)
    assert captured["code"] == ["code-9"]
    assert captured["code_verifier"] == [_VERIFIER]
    assert captured["client_secret"] == ["ghsecret"]
    assert captured["grant_type"] == ["authorization_code"]


def test_exchange_raises_on_provider_error() -> None:
    provider = _mock_github(lambda request: httpx.Response(200, json={"error": "bad_verification_code"}))
    with pytest.raises(OAuthProviderError):
        provider.exchange_code("nope", _VERIFIER)


def test_exchange_raises_on_http_error() -> None:
    provider = _mock_github(lambda request: httpx.Response(503, json={"error": "down"}))
    with pytest.raises(OAuthProviderError):
        provider.exchange_code("code", _VERIFIER)


# ---------------------------------------------------------------- profiles


def test_google_profile_parses_userinfo() -> None:
    provider = _mock_google(
        {"sub": "112233", "email": "abby@example.com", "email_verified": True, "name": "Abby", "picture": "https://img/a.png"}
    )
    profile = provider.fetch_profile("at-1")
    assert profile.provider == "google"
    assert profile.provider_account_id == "112233"
    assert profile.email == "abby@example.com"
    assert profile.display_name == "Abby"
    assert profile.avatar_url == "https://img/a.png"


def test_github_profile_uses_id_and_login() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer at-1"
        return httpx.Response(200, json={"id": 42, "login": "abby", "email": "abby@example.com"})

    profile = _mock_github(handler).fetch_profile("at-1")
    assert profile.provider_account_id == "42"
    assert profile.email == "abby@example.com"
    assert profile.display_name == "abby"


def test_github_profile_falls_back_to_primary_verified_email() -> None:
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 42, "login": "abby", "email": None})
        return httpx.Response(
            200,
            json=[
                {"email": "noise@example.com", "primary": False, "verified": True},
                {"email": "right@example.com", "primary": True, "verified": True},
            ],
        )

    profile = _mock_github(handler).fetch_profile("at-1")
    assert profile.email == "right@example.com"
    assert "/user/emails" in hits


def test_github_profile_with_private_email_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 7, "login": "ghost"})
        return httpx.Response(200, json=[])

    profile = _mock_github(handler).fetch_profile("at")
    assert profile.email == ""
    assert profile.provider_account_id == "7"
