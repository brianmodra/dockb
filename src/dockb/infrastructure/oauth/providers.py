"""Google and GitHub OAuth providers. See ``README_auth.md`` §5."""

from __future__ import annotations

import httpx

from dockb.infrastructure.oauth.provider import OAuthProfile, OAuthProvider, cast_str


class GoogleProvider(OAuthProvider):
    """Google via the OpenID Connect userinfo endpoint (``openid email profile``)."""

    name = "google"

    authorize_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    userinfo_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"
    scope = "openid email profile"
    authorize_params = {"access_type": "offline"}

    def fetch_profile(self, access_token: str) -> OAuthProfile:
        response = self._get(self.userinfo_endpoint, self._bearer_headers(access_token))
        data = self._json(response)
        return OAuthProfile(
            provider=self.name,
            provider_account_id=str(data["sub"]),
            email=data.get("email", ""),
            display_name=data.get("name", ""),
            avatar_url=data.get("picture", ""),
        )


class GitHubProvider(OAuthProvider):
    """GitHub via its REST API, with the user-email fallback for private emails."""

    name = "github"

    authorize_endpoint = "https://github.com/login/oauth/authorize"
    token_endpoint = "https://github.com/login/oauth/access_token"
    user_endpoint = "https://api.github.com/user"
    emails_endpoint = "https://api.github.com/user/emails"
    scope = "read:user user:email"

    def fetch_profile(self, access_token: str) -> OAuthProfile:
        headers = self._bearer_headers(access_token)
        data = self._json(self._get(self.user_endpoint, headers))
        email = cast_str(data.get("email")) or self._primary_email(headers)
        return OAuthProfile(
            provider=self.name,
            provider_account_id=str(data["id"]),
            email=email,
            display_name=cast_str(data.get("name")) or str(data.get("login", "")),
            avatar_url=cast_str(data.get("avatar_url")) or "",
        )

    def _primary_email(self, headers: dict[str, str]) -> str:
        emails = self._json(self._get(self.emails_endpoint, headers))
        for entry in emails:
            if entry.get("primary") and entry.get("verified"):
                return str(entry.get("email", ""))
        return ""


def make_google(client_id: str, client_secret: str, callback_port: int, http_client: httpx.Client | None = None) -> GoogleProvider:
    """Build a Google provider from its OAuth client credentials."""
    return GoogleProvider(client_id, client_secret, callback_port, http_client)


def make_github(client_id: str, client_secret: str, callback_port: int, http_client: httpx.Client | None = None) -> GitHubProvider:
    """Build a GitHub provider from its OAuth client credentials."""
    return GitHubProvider(client_id, client_secret, callback_port, http_client)
