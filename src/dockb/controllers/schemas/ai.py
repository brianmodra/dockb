"""POST /api/ai/chat schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """The user's prompt. Sent to the model as-is for now."""

    prompt: str = Field(min_length=1)


class ChatResponse(BaseModel):
    """The model's reply."""

    reply: str
