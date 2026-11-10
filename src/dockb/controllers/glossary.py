"""Document glossary routes — GET / PUT /api/documents/{document_id}/glossary.

The glossary is editor state, not manuscript content: it lives in the account SQLite
store, never in the graph, the markdown file, or a snapshot. A document the signed-in
account does not own is absent, exactly as it is on every other manuscript route.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_current_user, get_owner
from dockb.controllers.schemas.glossary import GlossaryRequest, GlossaryResponse
from dockb.exceptions import DocumentNotFoundError

router = APIRouter(prefix="/api/documents", tags=["glossary"])

_glossary_service: Any = None


def get_glossary_service() -> Any:
    return _glossary_service


def set_glossary_service(service: Any) -> None:
    global _glossary_service  # noqa: PLW0603
    _glossary_service = service


@router.get("/{document_id}/glossary")
def get_glossary(
    document_id: str,
    svc: Any = Depends(get_glossary_service),
    owner: str = Depends(get_owner),
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="glossary_service_unavailable")
    try:
        words = svc.get_words(document_id, owner=owner, username=user)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}") from exc
    return GlossaryResponse(words=words).model_dump()


@router.put("/{document_id}/glossary")
def put_glossary(
    document_id: str,
    body: GlossaryRequest,
    svc: Any = Depends(get_glossary_service),
    owner: str = Depends(get_owner),
    user: str = Depends(get_current_user),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="glossary_service_unavailable")
    try:
        words = svc.set_words(document_id, body.words, owner=owner, username=user)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"document_not_found: {document_id}") from exc
    return GlossaryResponse(words=words).model_dump()
