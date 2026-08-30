"""Tests for notification piggy-back helpers.

``collect_notifications`` drains the pending queue from a SessionContext
and normalises each Notification (or raw dict) into the wire format where
``type`` and payload fields sit at the top level of a plain dict.

``mutation_response`` wraps a MutationResponse with the collected
notifications, or returns ``None`` for the notifications key when
there is nothing pending.
"""

from __future__ import annotations

from dockb.services.session_context import Notification, SessionContext

# ---------------------------------------------------------------------------
# collect_notifications
# ---------------------------------------------------------------------------


class TestCollectNotifications:
    """Drain-and-normalise helper."""

    def test_none_context_returns_empty_list(self) -> None:
        from dockb.controllers.notifications import collect_notifications

        assert collect_notifications(None) == []

    def test_empty_queue_returns_empty_list(self) -> None:
        from dockb.controllers.notifications import collect_notifications

        ctx = SessionContext()
        assert collect_notifications(ctx) == []

    def test_single_notification_normalised(self) -> None:
        from dockb.controllers.notifications import collect_notifications

        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1", "changed_sentences": []}))
        result = collect_notifications(ctx)
        assert result == [{"type": "sentence_split", "paragraph_id": "p1", "changed_sentences": []}]

    def test_multiple_notifications(self) -> None:
        from dockb.controllers.notifications import collect_notifications

        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        ctx.add_notification(Notification(type="paragraph_split", payload={"chapter_id": "ch1"}))
        result = collect_notifications(ctx)
        assert len(result) == 2
        assert result[0]["type"] == "sentence_split"
        assert result[1]["type"] == "paragraph_split"

    def test_queue_cleared_after_collect(self) -> None:
        from dockb.controllers.notifications import collect_notifications

        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        collect_notifications(ctx)
        assert collect_notifications(ctx) == []

    def test_raw_dict_passthrough(self) -> None:
        """SessionContext.add_notification also accepts raw dicts."""
        from dockb.controllers.notifications import collect_notifications

        ctx = SessionContext()
        ctx.add_notification({"type": "sentence_split", "paragraph_id": "p2"})  # type: ignore[arg-type]
        result = collect_notifications(ctx)
        assert result == [{"type": "sentence_split", "paragraph_id": "p2"}]


# ---------------------------------------------------------------------------
# mutation_response
# ---------------------------------------------------------------------------


class TestMutationResponse:
    """Build a MutationResponse envelope with optional notifications."""

    def test_none_context_no_notifications_key(self) -> None:
        from dockb.controllers.notifications import mutation_response

        resp = mutation_response(None)
        assert resp.notifications is None

    def test_empty_queue_no_notifications_key(self) -> None:
        from dockb.controllers.notifications import mutation_response

        ctx = SessionContext()
        resp = mutation_response(ctx)
        assert resp.notifications is None

    def test_pending_notifications_attached(self) -> None:
        from dockb.controllers.notifications import mutation_response

        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        resp = mutation_response(ctx)
        notifications = list(resp.notifications or [])
        assert len(notifications) == 1
        first = notifications[0]
        assert first["type"] == "sentence_split"

    def test_queue_cleared_after_wrap(self) -> None:
        from dockb.controllers.notifications import mutation_response

        ctx = SessionContext()
        ctx.add_notification(Notification(type="sentence_split", payload={"paragraph_id": "p1"}))
        mutation_response(ctx)
        resp2 = mutation_response(ctx)
        assert resp2.notifications is None
