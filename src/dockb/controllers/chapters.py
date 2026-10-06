"""Chapter CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_current_user
from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.chapters import (
    ChapterDocumentRequest,
    ChapterDocumentResponse,
    ChapterImportSummaryWire,
    CreateChapterRequest,
    ReorderChapterRequest,
    UpdateChapterRequest,
)
from dockb.controllers.serializers import serialize_chapter
from dockb.exceptions import (
    ChapterAfterNotFoundError,
    ChapterCategoryMismatchError,
    DocumentNotFoundError,
    DuplicateTitleError,
)
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
    owner: str = Depends(get_current_user),
) -> Any:
    return svc.list_by_document(document, owner=owner)


@router.post("")
def create_chapter(
    body: CreateChapterRequest,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    try:
        svc.create(
            chapter_id=body.attrs.id,
            title=body.attrs.title,
            document_id=body.relations.document_id,
            after_chapter_id=body.relations.after_chapter_id,
            category=body.attrs.category,
            owner=owner,
        )
    except ChapterAfterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"after_chapter_not_found: {exc}") from exc
    except DocumentNotFoundError as exc:
        # A document of another account's is reported as one that does not exist,
        # which is what it is to this caller.
        raise HTTPException(status_code=404, detail=f"document_not_found: {exc}") from exc
    except DuplicateTitleError as exc:
        raise HTTPException(status_code=409, detail=f"chapter_title_conflict: {exc}") from exc
    return mutation_response(session_context).model_dump()


@router.get("/{chapter_id}")
def get_chapter(
    chapter_id: str,
    svc: Any = Depends(get_ch_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    ch = svc.open(chapter_id, owner=owner)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return serialize_chapter(ch).model_dump()


@router.get("/{chapter_id}/document")
def get_chapter_document(
    chapter_id: str,
    svc: Any = Depends(get_ch_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    content = svc.open_document(chapter_id, owner=owner)
    if content is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return ChapterDocumentResponse(content=content).model_dump()


@router.put("/{chapter_id}/document")
def put_chapter_document(
    chapter_id: str,
    body: ChapterDocumentRequest,
    svc: Any = Depends(get_ch_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    result = svc.save_document(chapter_id, body.content, owner=owner)
    if result is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    summary = result.summary
    return ChapterDocumentResponse(
        content=result.content,
        summary=ChapterImportSummaryWire(
            created=summary.created,
            changed=summary.changed,
            added=summary.added,
            deleted=summary.deleted,
        ),
    ).model_dump()


@router.post("/{chapter_id}/reorder")
def reorder_chapter(
    chapter_id: str,
    body: ReorderChapterRequest,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        ch = svc.move(chapter_id=chapter_id, after_chapter_id=body.after_chapter_id, owner=owner)
    except ChapterAfterNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"after_chapter_not_found: {exc}") from exc
    except ChapterCategoryMismatchError as exc:
        raise HTTPException(status_code=409, detail=f"chapter_category_mismatch: {exc}") from exc
    if ch is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return mutation_response(session_context).model_dump()


@router.put("/{chapter_id}")
def update_chapter(
    chapter_id: str,
    body: UpdateChapterRequest,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        ch = svc.update(chapter_id=chapter_id, title=body.attrs.title, owner=owner)
    except DuplicateTitleError as exc:
        raise HTTPException(status_code=409, detail=f"chapter_title_conflict: {exc}") from exc
    if ch is None:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{chapter_id}")
def delete_chapter(
    chapter_id: str,
    svc: Any = Depends(get_ch_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    deleted = svc.delete(chapter_id, owner=owner)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"chapter_not_found: {chapter_id}")
    return mutation_response(session_context).model_dump()
