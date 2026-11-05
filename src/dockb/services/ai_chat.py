"""AI chat: one prompt to OpenAI, one reply back, with the MCP server attached.

The prompt is sent through the Responses API. When ``DOCKB_MCP_PUBLIC_URL`` is
set and the shared per-prompt issuer is wired, the call carries DockB's MCP
endpoint as a tool with a bearer token minted just for this prompt, bound to
the signed-in account (``README_mcp_auth.md`` §2 and §3). The token travels
only in the tool's ``authorization`` field — never in model-visible text.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

import httpx2

logger = logging.getLogger(__name__)

_MODEL_ENV_VAR = "DOCKB_CHAT_MODEL"
_DEFAULT_MODEL = "gpt-4o-mini"
_KEY_ENV_VAR = "OPENAI_API_KEY"
_PUBLIC_URL_ENV_VAR = "DOCKB_MCP_PUBLIC_URL"

_MCP_SERVER_LABEL = "dockb"
_INSTRUCTIONS = (
    "You are the assistant in DockB's manuscript editor. DockB's MCP server "
    '(label "{label}") is attached to this request as a tool; call its tools '
    "directly whenever you need the user's manuscript — the endpoint is at "
    "{server_url} and its authorization is carried for you on the tool."
)


class MissingApiKeyError(RuntimeError):
    """No OPENAI_API_KEY is set, so no prompt can be sent."""


class AiChatService:  # pylint: disable=too-few-public-methods
    """Sends one prompt and answers the model's reply."""

    def __init__(
        self,
        complete: Any = None,
        token_issuer: Callable[[], Any] | None = None,
    ) -> None:
        self._complete = complete if complete is not None else self._default_complete
        self._token_issuer = token_issuer

    def complete(self, prompt: str, account_id: str = "") -> str:
        """Send *prompt* to the model and return its reply text.

        *account_id* scopes the per-prompt MCP bearer token minted for the
        call; without a public MCP URL the prompt is sent without MCP.
        """
        token: str | None = None
        server_url: str | None = None
        issuer = self._token_issuer() if self._token_issuer is not None else None
        public_url = os.environ.get(_PUBLIC_URL_ENV_VAR)
        if issuer is not None and public_url and public_url.strip():
            token = issuer.mint(uuid.uuid4().hex, account_id)
            server_url = f"{public_url.rstrip('/')}/mcp"
        return str(self._complete(prompt, token, server_url))

    def _default_complete(self, prompt: str, token: str | None, server_url: str | None) -> str:
        """One responses call with the configured model; MCP tool when it runs."""
        key = os.environ.get(_KEY_ENV_VAR)
        if not key or not key.strip():
            raise MissingApiKeyError("OPENAI_API_KEY is not set")
        payload: dict[str, Any] = {"model": os.environ.get(_MODEL_ENV_VAR, _DEFAULT_MODEL)}
        if server_url and token:
            payload["instructions"] = _INSTRUCTIONS.format(label=_MCP_SERVER_LABEL, server_url=server_url)
            payload["tools"] = [
                {
                    "type": "mcp",
                    "server_label": _MCP_SERVER_LABEL,
                    "server_url": server_url,
                    "authorization": token,
                    "require_approval": "never",
                }
            ]
        payload["input"] = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
        response = httpx2.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        reply = _reply_from(response.json())
        logger.info("AI reply: %s", reply)
        return reply


def _reply_from(payload: Any) -> str:
    """Collect the message items' output_text from a Responses-API payload."""
    texts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                texts.append(str(content.get("text", "")))
    return "\n".join(texts)
