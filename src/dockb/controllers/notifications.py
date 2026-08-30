"""Notification piggy-back helpers and poll endpoint.

Provides:
- ``collect_notifications``: drains the SessionContext queue into wire-format dicts.
- ``mutation_response``: wraps a MutationResponse with pending notifications.
- ``GET /api/notifications``: explicit poll endpoint.
- Shared SessionContext DI (``get_session_context`` / ``set_session_context``).
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from dockb.controllers.schemas.common import MutationResponse
from dockb.services.session_context import Notification, SessionContext

router = APIRouter(tags=["notifications"])

_session_context: SessionContext | None = None


def get_session_context() -> SessionContext | None:
    return _session_context


def set_session_context(ctx: SessionContext | None) -> None:
    global _session_context  # noqa: PLW0603
    _session_context = ctx


def _notification_to_dict(notification: Notification | dict[str, Any]) -> dict[str, Any]:
    """Normalise a Notification (or raw dict) to the wire format.

    Wire format has ``type`` and all payload fields at the top level.
    """
    if isinstance(notification, dict):
        return dict(notification)
    return {"type": notification.type, **notification.payload}


def collect_notifications(session_context: SessionContext | None) -> list[dict[str, Any]]:
    """Drain pending notifications and return as wire-format dicts."""
    if session_context is None:
        return []
    return [_notification_to_dict(n) for n in session_context.pending_notifications()]


def mutation_response(session_context: SessionContext | None) -> MutationResponse:
    """Build a MutationResponse with piggy-backed notifications."""
    notifications = collect_notifications(session_context)
    return MutationResponse(notifications=notifications if notifications else None)


@router.get("/api/notifications")
def get_notifications(
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    return {"notifications": collect_notifications(session_context)}
