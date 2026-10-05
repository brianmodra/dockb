"""Per-user session context with notification queue and processing state."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dockb.services.semantics.doc_cache import DocCache
    from dockb.services.semantics.job_queue import JobQueue


@dataclass
class Notification:
    """An async notification generated during semantic processing.

    Notifications are stored in the SessionContext queue and delivered to the
    client either piggy-backed on the next API response or via explicit poll.
    """

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


class SessionContext:
    """Holds per-user state for the duration of a logged-in session.

    Bundles the JobQueue, DocCache, and a pending notification queue for
    delivering async results (e.g. sentence splits from ReconstructJob) to
    the client.

    ``created_at`` is when the session began, and is what ``users.credentials_changed_at``
    is compared against to invalidate a session the CLI cannot reach. It is stamped by
    ``SessionManager``, which owns the clock.
    """

    def __init__(
        self,
        job_queue: JobQueue | None = None,
        doc_cache: DocCache | None = None,
        *,
        created_at: datetime | None = None,
    ) -> None:
        self.job_queue = job_queue
        self.doc_cache = doc_cache
        self._created_at = created_at or datetime.now(timezone.utc)
        self._notifications: list[Notification] = []

    @property
    def created_at(self) -> datetime:
        """When this session began, timezone-aware UTC."""
        return self._created_at

    def add_notification(self, notification: Notification) -> None:
        """Enqueue a notification for delivery to the client."""
        self._notifications.append(notification)

    def pending_notifications(self) -> Sequence[Notification]:
        """Return all pending notifications and clear the queue."""
        pending = list(self._notifications)
        self._notifications.clear()
        return pending
