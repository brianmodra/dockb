"""Paragraph CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.desugar import desugar_sentences
from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.paragraphs import CreateParagraphRequest, UpdateParagraphRequest
from dockb.controllers.serializers import serialize_paragraph
from dockb.services.session_context import SessionContext

router = APIRouter(prefix="/api/paragraphs", tags=["paragraphs"])

_para_service: Any = None


def get_para_service() -> Any:
    return _para_service


def set_para_service(service: Any) -> None:
    global _para_service  # noqa: PLW0603
    _para_service = service


@router.get("")
def list_paragraphs(
    chapter: str,
    svc: Any = Depends(get_para_service),
) -> Any:
    return svc.list_by_chapter(chapter)


@router.post("")
def create_paragraph(
    body: CreateParagraphRequest,
    svc: Any = Depends(get_para_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    sentences = desugar_sentences(body.content)
    svc.create(
        paragraph_id=body.attrs.id,
        content=sentences,
        chapter_id=body.relations.chapter_id,
    )
    return mutation_response(session_context).model_dump()


@router.get("/{paragraph_id}")
def get_paragraph(
    paragraph_id: str,
    svc: Any = Depends(get_para_service),
) -> dict[str, Any]:
    para = svc.get(paragraph_id)
    if para is None:
        raise HTTPException(status_code=404, detail=f"paragraph_not_found: {paragraph_id}")
    return serialize_paragraph(para).model_dump()


@router.put("/{paragraph_id}")
def update_paragraph(
    paragraph_id: str,
    body: UpdateParagraphRequest,
    svc: Any = Depends(get_para_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    sentences = desugar_sentences(body.content)
    chapter_id = body.relations.chapter_id if body.relations else None
    para = svc.update(
        paragraph_id=paragraph_id,
        content=sentences,
        chapter_id=chapter_id,
    )
    if para is None:
        raise HTTPException(status_code=404, detail=f"paragraph_not_found: {paragraph_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{paragraph_id}")
def delete_paragraph(
    paragraph_id: str,
    svc: Any = Depends(get_para_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    deleted = svc.delete(paragraph_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"paragraph_not_found: {paragraph_id}")
    return mutation_response(session_context).model_dump()
