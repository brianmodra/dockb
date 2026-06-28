from dockb.services.session_context import Notification, SessionContext


def test_notification_created_with_type():
    notification = Notification(type="sentence_split", payload={"paragraph_id": "p1"})
    assert notification.type == "sentence_split"


def test_notification_has_payload():
    notification = Notification(
        type="sentence_split",
        payload={"paragraph_id": "p1", "changed_sentences": []},
    )
    assert notification.payload["paragraph_id"] == "p1"


def test_session_context_starts_with_no_notifications():
    ctx = SessionContext()
    assert not ctx.pending_notifications()


def test_can_add_single_notification():
    ctx = SessionContext()
    notification = Notification(type="sentence_split", payload={"paragraph_id": "p1"})
    ctx.add_notification(notification)
    result = ctx.pending_notifications()
    assert len(result) == 1
    assert result[0].type == "sentence_split"


def test_pending_notifications_clears_queue():
    ctx = SessionContext()
    ctx.add_notification(Notification(type="sentence_split", payload={}))
    first = ctx.pending_notifications()
    assert len(first) == 1
    second = ctx.pending_notifications()
    assert not second


def test_notifications_fifo_order():
    ctx = SessionContext()
    n1 = Notification(type="sentence_split", payload={"id": "first"})
    n2 = Notification(type="paragraph_split", payload={"id": "second"})
    ctx.add_notification(n1)
    ctx.add_notification(n2)
    result = ctx.pending_notifications()
    assert len(result) == 2
    assert result[0].payload["id"] == "first"
    assert result[1].payload["id"] == "second"


def test_add_notification_after_clear_returns_new():
    ctx = SessionContext()
    ctx.add_notification(Notification(type="sentence_split", payload={}))
    ctx.pending_notifications()
    ctx.add_notification(Notification(type="paragraph_split", payload={}))
    result = ctx.pending_notifications()
    assert len(result) == 1
    assert result[0].type == "paragraph_split"


def test_multiple_notifications_of_same_type():
    ctx = SessionContext()
    n1 = Notification(type="sentence_split", payload={"paragraph_id": "p1"})
    n2 = Notification(type="sentence_split", payload={"paragraph_id": "p2"})
    ctx.add_notification(n1)
    ctx.add_notification(n2)
    result = ctx.pending_notifications()
    assert len(result) == 2
    assert result[0].payload["paragraph_id"] == "p1"
    assert result[1].payload["paragraph_id"] == "p2"
