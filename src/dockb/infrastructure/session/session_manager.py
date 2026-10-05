"""Per-user session context lifecycle management."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from dockb.services.session_context import SessionContext

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages creation, lookup, and cleanup of SessionContext objects.

    Each authenticated user has one SessionContext that persists for the
    duration of their logged-in session. The SessionManager is a long-lived
    singleton created at app startup.

    It also owns the session clock. A session's creation time is what
    ``users.credentials_changed_at`` is compared against to invalidate a session the
    admin CLI cannot reach, and comparing the two needs both values to be
    timezone-aware UTC — the same shape the store writes its stamps in. The clock is
    injected so tests can place a session either side of a credential change without
    sleeping.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._contexts: dict[str, SessionContext] = {}

    def get(self, account_id: str) -> SessionContext | None:
        """Return the SessionContext for a given account ID, or None."""
        return self._contexts.get(account_id)

    def create(self, account_id: str) -> SessionContext:
        """Create and store a new SessionContext for the given account ID."""
        ctx = SessionContext(created_at=self._clock())
        self._contexts[account_id] = ctx
        return ctx

    def remove(self, account_id: str) -> None:
        """Remove and clean up the SessionContext for the given account ID."""
        self._contexts.pop(account_id, None)
