"""Per-user app-state routes: GET and PUT /api/app/state.

State is keyed to the authenticated user from the session cookie and stored in
the SQLite ``app_state`` table; ``panel_widths`` is transported as a JSON
object and serialized to the TEXT column. See ``README_auth.md`` §6 step 5 and
``README_markdown_editor_ui.md`` §9.
"""

# pylint: disable=invalid-name,missing-function-docstring

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Depends

from dockb.controllers.auth import get_auth_service, get_current_user
from dockb.controllers.schemas.app_state import AppStateRequest, AppStateResponse

router = APIRouter(prefix="/api/app", tags=["app-state"])


def _to_response(row: dict[str, object] | None) -> AppStateResponse:
    if row is None:
        return AppStateResponse()
    panel_widths: dict[str, int] | None = None
    raw_widths = row.get("panel_widths")
    if raw_widths is not None:
        try:
            panel_widths = json.loads(str(raw_widths))
        except json.JSONDecodeError:
            panel_widths = None
    return AppStateResponse(
        last_document_id=cast(str | None, row.get("last_document_id")),
        panel_widths=panel_widths,
        edit_mode=cast(str | None, row.get("edit_mode")),
    )


@router.get("/state")
def get_app_state(
    user_id: str = Depends(get_current_user),
    svc: Any = Depends(get_auth_service),
) -> AppStateResponse:
    return _to_response(svc.get_app_state(user_id))


@router.put("/state")
def put_app_state(
    body: AppStateRequest,
    user_id: str = Depends(get_current_user),
    svc: Any = Depends(get_auth_service),
) -> AppStateResponse:
    svc.set_app_state(
        user_id,
        {
            "last_document_id": body.last_document_id,
            "panel_widths": None if body.panel_widths is None else json.dumps(body.panel_widths),
            "edit_mode": body.edit_mode,
        },
    )
    return _to_response(svc.get_app_state(user_id))
