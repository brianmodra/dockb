"""Build OAuth providers from environment configuration. See ``README_auth.md`` §5."""

from __future__ import annotations

import os

import httpx

from dockb.infrastructure.oauth.provider import OAuthProvider
from dockb.infrastructure.oauth.providers import GitHubProvider, GoogleProvider

_DEFAULT_CALLBACK_PORT = 8000

_PROVIDER_ENV_PAIRS: dict[str, tuple[str, str]] = {
    "google": ("OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET"),
    "github": ("OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET"),
}


def build_provider(
    name: str,
    client_id: str,
    client_secret: str,
    callback_port: int,
    http_client: httpx.Client | None = None,
) -> OAuthProvider:
    """Construct the named provider from its OAuth client credentials."""
    if name == "google":
        return GoogleProvider(client_id, client_secret, callback_port, http_client)
    if name == "github":
        return GitHubProvider(client_id, client_secret, callback_port, http_client)
    raise ValueError(f"unsupported oauth provider: {name}")


def providers_from_env(http_client: httpx.Client | None = None) -> dict[str, OAuthProvider]:
    """Return every provider whose env credentials are present, keyed by name."""
    port = int(os.environ.get("OAUTH_CALLBACK_PORT", str(_DEFAULT_CALLBACK_PORT)))
    providers: dict[str, OAuthProvider] = {}
    for name, (client_id_key, client_secret_key) in _PROVIDER_ENV_PAIRS.items():
        client_id = os.environ.get(client_id_key)
        client_secret = os.environ.get(client_secret_key)
        if client_id and client_secret:
            providers[name] = build_provider(name, client_id, client_secret, port, http_client)
    return providers
