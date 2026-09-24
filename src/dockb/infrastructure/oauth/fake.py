"""A deterministic, network-free provider used by integration tests of the auth flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dockb.infrastructure.oauth.provider import OAuthProfile, OAuthProvider, TokenResult
from dockb.infrastructure.oauth.providers import GoogleProvider


class FakeOAuthProvider(OAuthProvider):
    """Behaves like a real provider but never touches the network."""

    name = "fake"

    authorize_endpoint = "https://fake.example/authorize"
    token_endpoint = "https://fake.example/token"
    scope = "openid email profile"
    authorize_params = GoogleProvider.authorize_params

    def __init__(  # pylint: disable=too-many-arguments
        self,
        client_id: str = "fake-client",
        client_secret: str = "fake-secret",
        callback_port: int = 8123,
        *,
        provider_account_id: str = "fake-1",
        username: str = "fake-user",
        email: str = "fake@example.com",
        display_name: str = "Fake User",
        avatar_url: str = "https://fake.example/avatar.png",
    ) -> None:
        super().__init__(client_id, client_secret, callback_port)
        self._account_id = provider_account_id
        self._username = username
        self._email = email
        self._display_name = display_name
        self._avatar_url = avatar_url

    def exchange_code(self, code: str, code_verifier: str) -> TokenResult:
        return TokenResult(
            access_token=f"access-token-for-{code}",
            refresh_token="fake-refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    def fetch_profile(self, access_token: str) -> OAuthProfile:
        return OAuthProfile(
            provider=self.name,
            provider_account_id=self._account_id,
            username=self._username,
            email=self._email,
            display_name=self._display_name,
            avatar_url=self._avatar_url,
        )
