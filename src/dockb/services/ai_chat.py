"""AI chat: one prompt to OpenAI, one reply back."""

from __future__ import annotations

import os
from typing import Any

import httpx2

_MODEL_ENV_VAR = "DOCKB_CHAT_MODEL"
_DEFAULT_MODEL = "gpt-4o-mini"
_KEY_ENV_VAR = "OPENAI_API_KEY"


class MissingApiKeyError(RuntimeError):
    """No OPENAI_API_KEY is set, so no prompt can be sent."""


class AiChatService:  # pylint: disable=too-few-public-methods
    """Sends one prompt and answers the model's reply."""

    def __init__(self, complete: Any = None) -> None:
        self._complete = complete if complete is not None else _openai_complete

    def complete(self, prompt: str) -> str:
        """Send *prompt* to the model and return its reply text."""
        return str(self._complete(prompt))


def _openai_complete(prompt: str) -> str:
    """One chat-completion with the configured model."""
    key = os.environ.get(_KEY_ENV_VAR)
    if not key or not key.strip():
        raise MissingApiKeyError("OPENAI_API_KEY is not set")
    response = httpx2.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.environ.get(_MODEL_ENV_VAR, _DEFAULT_MODEL),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"])
