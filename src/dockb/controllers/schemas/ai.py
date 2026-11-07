"""POST /api/ai/chat schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """The user's prompt, and the manuscript they have open (sent to the model as-is)."""

    prompt: str = Field(min_length=1)
    document_id: str | None = None


class ChatResponse(BaseModel):
    """The model's reply."""

    reply: str
