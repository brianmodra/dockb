"""Document CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.documents import CreateDocumentRequest, UpdateDocumentRequest
from dockb.controllers.serializers import serialize_document
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
) -> Any:
    summaries = svc.list_all()
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
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    svc.create(
        document_id=body.attrs.id,
        title=body.attrs.title,
        author=body.attrs.author,
    )
    return mutation_response(session_context).model_dump()


@router.get("/{document_id}")
def get_document(
    document_id: str,
    svc: Any = Depends(get_doc_service),
) -> dict[str, Any]:
    doc = svc.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return serialize_document(doc)


@router.put("/{document_id}")
def update_document(
    document_id: str,
    body: UpdateDocumentRequest,
    svc: Any = Depends(get_doc_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    doc = svc.update(
        document_id=document_id,
        title=body.attrs.title,
        author=body.attrs.author,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    svc: Any = Depends(get_doc_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    deleted = svc.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}")
    return mutation_response(session_context).model_dump()
