"""Document CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_current_user
from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.documents import CreateDocumentRequest, UpdateDocumentRequest
from dockb.controllers.serializers import serialize_document
from dockb.exceptions import DocumentOwnershipError, DuplicateTitleError
from dockb.services.session_context import SessionContext

router = APIRouter(prefix="/api/documents", tags=["documents"])

_doc_service: Any = None


def get_doc_service() -> Any:
    return _doc_service


def set_doc_service(service: Any) -> None:
    global _doc_service  # noqa: PLW0603
    _doc_service = service


@router.get("")
def list_documents(
    svc: Any = Depends(get_doc_service),
    owner: str = Depends(get_current_user),
) -> Any:
    summaries = svc.list_all(owner=owner)
    return [
        {
            "attrs": {"id": s["id"], "title": s["title"], "author": s["author"]},
            "chapter_summaries": [],
        }
        for s in summaries
    ]


@router.post("")
def create_document(
    body: CreateDocumentRequest,
    svc: Any = Depends(get_doc_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    try:
        svc.create(
            document_id=body.attrs.id,
            title=body.attrs.title,
            author=body.attrs.author,
            owner=owner,
        )
    except DuplicateTitleError as exc:
        raise HTTPException(status_code=409, detail=f"document_title_conflict: {exc}") from exc
    except DocumentOwnershipError as exc:
        # A session resolves to an account, so this is a fault of ours rather than
        # something the caller did; saying so keeps a broken session from looking
        # like a document that could not be created.
        raise HTTPException(status_code=500, detail=f"document_ownership_unavailable: {exc}") from exc
    return mutation_response(session_context).model_dump()


@router.get("/{document_id}")
def get_document(
    document_id: str,
    svc: Any = Depends(get_doc_service),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    doc = svc.open(document_id, owner=owner)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return serialize_document(doc)


@router.put("/{document_id}")
def update_document(
    document_id: str,
    body: UpdateDocumentRequest,
    svc: Any = Depends(get_doc_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        doc = svc.update(
            document_id=document_id,
            title=body.attrs.title,
            author=body.attrs.author,
            owner=owner,
        )
    except DuplicateTitleError as exc:
        raise HTTPException(status_code=409, detail=f"document_title_conflict: {exc}") from exc
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    svc: Any = Depends(get_doc_service),
    session_context: SessionContext | None = Depends(get_session_context),
    owner: str = Depends(get_current_user),
) -> dict[str, Any]:
    deleted = svc.delete(document_id, owner=owner)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return mutation_response(session_context).model_dump()
