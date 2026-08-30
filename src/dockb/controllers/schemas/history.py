"""History API request / response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class Snapshot(BaseModel):
    """A single history entry (most recent first)."""

    datetime: str
    commit_id: str


class HistoryResponse(BaseModel):
    """GET /api/history/{chapter_id} response."""

    snapshots: list[Snapshot]


class RestoreRequest(BaseModel):
    """PATCH /api/history/{chapter_id} request body."""

    commit_id: str
