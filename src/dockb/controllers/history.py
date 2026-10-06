"""History routes — GET/PATCH /api/history/{chapter_id}."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_current_user
from dockb.controllers.schemas.history import HistoryResponse, RestoreRequest, Snapshot
from dockb.controllers.serializers import serialize_chapter

router = APIRouter(prefix="/api/history", tags=["history"])

_history_service: Any = None


def get_history_service() -> Any:
    return _history_service


def set_history_service(service: Any) -> None:
    global _history_service  # noqa: PLW0603
    _history_service = service


@router.get("/{chapter_id}")
def list_history(
    chapter_id: str,
    limit: int = 20,
    offset: int = 0,
    svc: Any = Depends(get_history_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    snapshots = svc.list_snapshots(chapter_id, owner=owner, limit=limit, offset=offset)
    return HistoryResponse(snapshots=[Snapshot(**s) for s in snapshots]).model_dump()


@router.patch("/{chapter_id}")
def restore_chapter(
    chapter_id: str,
    body: RestoreRequest,
    svc: Any = Depends(get_history_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        chapter = svc.restore(chapter_id, body.commit_id, owner=owner)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"restore_failed: {exc}") from exc
    if chapter is None:
        # The snapshot store is shared and keyed by chapter id alone, so a chapter of
        # another account's is refused here; it answers as one that does not exist.
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return serialize_chapter(chapter).model_dump()
