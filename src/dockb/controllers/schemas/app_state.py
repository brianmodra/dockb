"""GET/PUT /api/app/state schemas — per-user editor state.

The three fields are opaque storage from the backend's point of view:
``panel_widths`` is a free-form JSON object, ``edit_mode`` an open string,
``last_document_id`` a document id. See ``README_auth.md`` §3.
"""

from __future__ import annotations

from pydantic import BaseModel


class AppStateRequest(BaseModel):
    """PUT /api/app/state request body; every field is optional."""

    last_document_id: str | None = None
    panel_widths: dict[str, int] | None = None
    edit_mode: str | None = None


class AppStateResponse(BaseModel):
    """GET/PUT /api/app/state payload."""

    last_document_id: str | None = None
    panel_widths: dict[str, int] | None = None
    edit_mode: str | None = None
