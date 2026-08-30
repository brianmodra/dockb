"""Tests for history request / response schemas."""

from dockb.controllers.schemas.history import HistoryResponse, RestoreRequest, Snapshot


def test_snapshot():
    s = Snapshot(datetime="2025-01-15T10:30:00Z", commit_id="abc123")
    d = s.model_dump()
    assert d == {"datetime": "2025-01-15T10:30:00Z", "commit_id": "abc123"}


def test_history_response():
    r = HistoryResponse(
        snapshots=[
            Snapshot(datetime="2025-01-15T10:30:00Z", commit_id="abc"),
            Snapshot(datetime="2025-01-14T09:00:00Z", commit_id="def"),
        ]
    )
    assert len(r.snapshots) == 2
    assert r.snapshots[0].commit_id == "abc"


def test_history_response_empty():
    r = HistoryResponse(snapshots=[])
    assert r.snapshots == []


def test_restore_request():
    req = RestoreRequest(commit_id="abc123")
    assert req.commit_id == "abc123"
