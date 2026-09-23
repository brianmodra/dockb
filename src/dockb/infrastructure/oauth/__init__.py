"""OAuth Authorization Code + PKCE provider layer (Google, GitHub, fake)."""

from dockb.infrastructure.oauth.factory import build_provider, providers_from_env
from dockb.infrastructure.oauth.fake import FakeOAuthProvider
from dockb.infrastructure.oauth.pkce import create_code_verifier, s256_challenge
from dockb.infrastructure.oauth.provider import OAuthProfile, OAuthProvider, OAuthProviderError, TokenResult

__all__ = [
    "OAuthProfile",
    "OAuthProvider",
    "OAuthProviderError",
    "TokenResult",
    "FakeOAuthProvider",
    "build_provider",
    "providers_from_env",
    "create_code_verifier",
    "s256_challenge",
]
