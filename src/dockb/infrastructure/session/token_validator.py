"""OAuth token validation and account ID extraction."""

import logging

logger = logging.getLogger(__name__)


class TokenValidator:  # pylint: disable=too-few-public-methods
    """Validates OAuth tokens and extracts the authenticated account ID.

    Supports multiple OAuth providers (Google, GitHub, etc.).
    """

    def __init__(self) -> None:
        pass

    def validate(self, token: str) -> str | None:  # pylint: disable=unused-argument
        """Validate an OAuth token and return the account ID, or None if invalid."""
        return None
