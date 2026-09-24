"""OAuth 2.0 Authorization Code + PKCE providers: Google, GitHub, and a fake for tests.

The backend is the confidential OAuth client. Providers differ only in consent URL,
token endpoint, scopes, and profile parsing; the base class builds the authorization
URL and runs the code exchange generically. See ``README_auth.md``.
"""

from __future__ import annotations

import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from dockb.infrastructure.oauth.pkce import s256_challenge


class OAuthProviderError(RuntimeError):
    """Raised when a provider rejects an exchange or a profile request."""


@dataclass(frozen=True)
class OAuthProfile:
    """Normalized profile fields every provider resolves to."""

    provider: str
    provider_account_id: str
    username: str
    email: str
    display_name: str
    avatar_url: str


@dataclass(frozen=True)
class TokenResult:
    """Tokens returned by the code exchange, with the computed access-token expiry."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None


class OAuthProvider(ABC):
    """Interface (and shared flow) for a confidential OAuth provider."""

    name: str = ""

    authorize_endpoint: str = ""
    token_endpoint: str = ""
    scope: str = ""
    authorize_params: dict[str, str] = {}

    def __init__(self, client_id: str, client_secret: str, callback_port: int, http_client: httpx.Client | None = None) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_port = callback_port
        self._http = http_client

    @property
    def redirect_uri(self) -> str:
        """The loopback callback URI registered with the provider."""
        return f"http://localhost:{self.callback_port}/callback"

    def authorization_url(self, state: str, code_verifier: str) -> str:
        """Build the consent URL carrying *state* and the S256 PKCE challenge."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
            "code_challenge": s256_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
        params.update(self.authorize_params)
        query = urllib.parse.urlencode(params)
        return f"{self.authorize_endpoint}?{query}"

    def exchange_code(self, code: str, code_verifier: str) -> TokenResult:
        """Exchange *code* for tokens, presenting *code_verifier*."""
        data = self._json(
            self._post(
                self.token_endpoint,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
        )
        expires_at = None
        if isinstance(data.get("expires_in"), int):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        return TokenResult(
            access_token=str(data["access_token"]),
            refresh_token=cast_str(data.get("refresh_token")),
            expires_at=expires_at,
        )

    @abstractmethod
    def fetch_profile(self, access_token: str) -> OAuthProfile:
        """Fetch the user's normalized profile with *access_token*."""

    # ------------------------------------------------------------------ http

    def _get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        if self._http is not None:
            return self._http.get(url, headers=headers)
        with httpx.Client() as client:
            return client.get(url, headers=headers)

    def _post(self, url: str, data: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        if self._http is not None:
            return self._http.post(url, data=data, headers=headers)
        with httpx.Client() as client:
            return client.post(url, data=data, headers=headers)

    def _json(self, response: httpx.Response) -> Any:
        data = response.json()
        if not response.is_success or (isinstance(data, dict) and data.get("error")):
            raise OAuthProviderError(f"{self.name} request failed: {data!r}")
        return data

    @staticmethod
    def _bearer_headers(access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def cast_str(value: Any) -> str | None:
    """Return *value* as str, or None."""
    return value if isinstance(value, str) else None
