"""Tests for common envelope schemas."""

from dockb.controllers.schemas.common import ErrorResponse, MutationResponse, Status


def test_status_defaults():
    s = Status()
    assert s.code == "ok"
    assert s.message == "success"


def test_status_custom():
    s = Status(code="not_found", message="no such item")
    assert s.code == "not_found"


def test_mutation_response_defaults():
    r = MutationResponse()
    assert r.status.code == "ok"  # pylint: disable=no-member
    assert r.notifications is None


def test_mutation_response_with_notifications():
    r = MutationResponse(notifications=[{"type": "sentence_split", "paragraph_id": "p1"}])
    assert len(r.notifications) == 1
    assert r.notifications[0]["type"] == "sentence_split"  # pylint: disable=unsubscriptable-object


def test_error_response():
    r = ErrorResponse(status=Status(code="document_not_found", message="No document with id 'd-1'."))
    assert r.status.code == "document_not_found"
    assert r.status.message == "No document with id 'd-1'."
