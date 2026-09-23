"""Tests for the env-configuration factory and the fake provider."""

from __future__ import annotations

import urllib.parse

import pytest

from dockb.infrastructure.oauth.factory import build_provider, providers_from_env
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.provider import OAuthProvider
from dockb.infrastructure.oauth.providers import GitHubProvider, GoogleProvider


def test_providers_from_env_skips_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("OAUTH_CALLBACK_PORT", raising=False)
    for key in ("OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET", "OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert not providers_from_env()


def test_providers_from_env_builds_only_configured(monkeypatch) -> None:
    monkeypatch.delenv("OAUTH_CALLBACK_PORT", raising=False)
    for key in ("OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET", "OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "google-secret")
    providers = providers_from_env()
    assert set(providers) == {"google"}
    provider = providers["google"]
    assert provider.client_id == "google-id"
    assert provider.redirect_uri.endswith("/callback")


def test_providers_from_env_uses_callback_port(monkeypatch) -> None:
    monkeypatch.setenv("OAUTH_CALLBACK_PORT", "9123")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "secret")
    provider = providers_from_env()["google"]
    assert provider.callback_port == 9123
    assert provider.redirect_uri == "http://localhost:9123/callback"


@pytest.mark.parametrize(
    ("name", "provider_type"),
    [("google", GoogleProvider), ("github", GitHubProvider)],
)
def test_build_provider_constructs_named_provider(name, provider_type) -> None:
    provider = build_provider(name, "cid", "csecret", 8123)
    assert isinstance(provider, provider_type)
    assert isinstance(provider, OAuthProvider)


def test_build_provider_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        build_provider("myspace", "cid", "csecret", 8123)


def test_fake_provider_builds_consent_url_with_pkce() -> None:
    provider = FakeOAuthProvider()
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(provider.authorization_url("s1", "v1")).query)
    assert params["state"] == ["s1"]
    assert params["code_challenge"] is not None
    assert params["code_challenge_method"] == ["S256"]


def test_fake_provider_exchange_and_profile() -> None:
    provider = FakeOAuthProvider(email="real@example.com")
    result = provider.exchange_code("c1", "v1")
    assert result.access_token == "access-token-for-c1"
    assert result.refresh_token == "fake-refresh-token"
    profile = provider.fetch_profile(result.access_token)
    assert profile.provider == "fake"
    assert profile.provider_account_id == "fake-1"
    assert profile.email == "real@example.com"
