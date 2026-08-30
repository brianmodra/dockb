"""Chapter CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.chapters import CreateChapterRequest, UpdateChapterRequest
from dockb.controllers.serializers import serialize_chapter
from dockb.services.session_context import SessionContext

router = APIRouter(prefix="/api/chapters", tags=["chapters"])

_ch_service: Any = None


def get_ch_service() -> Any:
    return _ch_service


def set_ch_service(service: Any) -> None:
    global _ch_service  # noqa: PLW0603
    _ch_service = service


@router.get("")
def list_chapters(
    document: str,
    svc: Any = Depends(get_ch_service),
) -> Any:
    return svc.list_by_document(document)


@router.post("")
def create_chapter(
    body: CreateChapterRequest,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    svc.create(
        chapter_id=body.attrs.id,
        title=body.attrs.title,
        document_id=body.relations.document_id,
    )
    return mutation_response(session_context).model_dump()


@router.get("/{chapter_id}")
def get_chapter(
    chapter_id: str,
    svc: Any = Depends(get_ch_service),
) -> dict[str, Any]:
    ch = svc.get(chapter_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return serialize_chapter(ch).model_dump()


@router.put("/{chapter_id}")
def update_chapter(
    chapter_id: str,
    body: UpdateChapterRequest,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    ch = svc.update(chapter_id=chapter_id, title=body.attrs.title)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{chapter_id}")
def delete_chapter(
    chapter_id: str,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    deleted = svc.delete(chapter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return mutation_response(session_context).model_dump()
