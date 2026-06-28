"""Per-user session context lifecycle management."""

import logging

from dockb.services.session_context import SessionContext

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages creation, lookup, and cleanup of SessionContext objects.

    Each authenticated user has one SessionContext that persists for the
    duration of their logged-in session. The SessionManager is a long-lived
    singleton created at app startup.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, SessionContext] = {}

    def get(self, account_id: str) -> SessionContext | None:  # pylint: disable=unused-argument
        """Return the SessionContext for a given account ID, or None."""
        return self._contexts.get(account_id)

    def create(self, account_id: str) -> SessionContext:
        """Create and store a new SessionContext for the given account ID."""
        ctx = SessionContext()
        self._contexts[account_id] = ctx
        return ctx

    def remove(self, account_id: str) -> None:
        """Remove and clean up the SessionContext for the given account ID."""
        self._contexts.pop(account_id, None)
