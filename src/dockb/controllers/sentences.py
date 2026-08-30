"""Sentence CRUD routes."""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.desugar import extract_text_from_nodes
from dockb.controllers.notifications import get_session_context, mutation_response
from dockb.controllers.schemas.sentences import CreateSentenceRequest, UpdateSentenceRequest
from dockb.controllers.serializers import serialize_sentence
from dockb.services.session_context import SessionContext

router = APIRouter(prefix="/api/sentences", tags=["sentences"])

_sent_service: Any = None


def get_sent_service() -> Any:
    return _sent_service


def set_sent_service(service: Any) -> None:
    global _sent_service  # noqa: PLW0603
    _sent_service = service


@router.get("")
def list_sentences(
    paragraph: str,
    svc: Any = Depends(get_sent_service),
) -> Any:
    return svc.list_by_paragraph(paragraph)


@router.post("")
def create_sentence(
    body: CreateSentenceRequest,
    svc: Any = Depends(get_sent_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    if body.attrs.id is None:
        raise HTTPException(status_code=422, detail="attrs.id is required")
    text = extract_text_from_nodes(body.content)
    svc.create(
        sentence_id=body.attrs.id,
        text=text,
        paragraph_id=body.relations.paragraph_id,
    )
    return mutation_response(session_context).model_dump()


@router.get("/{sentence_id}")
def get_sentence(
    sentence_id: str,
    svc: Any = Depends(get_sent_service),
) -> dict[str, Any]:
    sent = svc.get(sentence_id)
    if sent is None:
        raise HTTPException(status_code=404, detail=f"sentence_not_found: {sentence_id}")
    return serialize_sentence(sent).model_dump()


@router.put("/{sentence_id}")
def update_sentence(
    sentence_id: str,
    body: UpdateSentenceRequest,
    svc: Any = Depends(get_sent_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    text = extract_text_from_nodes(body.content)
    paragraph_id = body.relations.paragraph_id if body.relations else None
    sent = svc.update(
        sentence_id=sentence_id,
        text=text,
        paragraph_id=paragraph_id,
    )
    if sent is None:
        raise HTTPException(status_code=404, detail=f"sentence_not_found: {sentence_id}")
    return mutation_response(session_context).model_dump()


@router.delete("/{sentence_id}")
def delete_sentence(
    sentence_id: str,
    svc: Any = Depends(get_sent_service),
    session_context: SessionContext | None = Depends(get_session_context),
) -> dict[str, Any]:
    deleted = svc.delete(sentence_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"sentence_not_found: {sentence_id}")
    return mutation_response(session_context).model_dump()
