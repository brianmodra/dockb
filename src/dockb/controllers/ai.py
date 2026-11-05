"""AI chat route — POST /api/ai/chat.

One editor prompt in, one model reply out. The prompt is sent to OpenAI as-is
for now (no manuscript context yet); the OPENAI_API_KEY never leaves the
server.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from dockb.controllers.auth import get_owner
from dockb.controllers.schemas.ai import ChatRequest, ChatResponse
from dockb.services.ai_chat import MissingApiKeyError

router = APIRouter(prefix="/api/ai", tags=["ai"])

_ai_service: Any = None


def get_ai_service() -> Any:
    return _ai_service


def set_ai_service(service: Any) -> None:
    global _ai_service  # noqa: PLW0603
    _ai_service = service


@router.post("/chat")
def chat(
    body: ChatRequest,
    svc: Any = Depends(get_ai_service),
    owner: str = Depends(get_owner),
) -> dict[str, Any]:
    if svc is None:
        raise HTTPException(status_code=503, detail="ai_service_unavailable")
    try:
        reply = svc.complete(body.prompt, owner)
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=f"ai_key_missing: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ai_unavailable: {exc}") from exc
    return ChatResponse(reply=reply).model_dump()
