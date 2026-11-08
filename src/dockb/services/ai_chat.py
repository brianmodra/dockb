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
_DOCUMENT_INSTRUCTIONS = (
    " The user is viewing the manuscript whose document_id is " + '"{document_id}"; use it as the tools\' document_id argument.'
)
_RESPONSE_SYNTAX_INSTRUCTIONS = (
    " Reply with only the editor's response-syntax JSON object — no prose, no markdown, no"
    ' code fences. The object is {"response": [{"text": "what this paragraph says"},'
    ' {"button": {"label": "Show me this paragraph", "function": "highlight",'
    ' "args": {"chapter_id": "<the chapter id>", "paragraph_id": "<the paragraph id>",'
    ' "sentence_indices": [<sentence positions> | []]}}}]}. A text-only answer is'
    ' {"response": [{"text": "..."}]}. The response array must never be empty: when nothing'
    ' answers, include a text item that says so. Use one "text" item per paragraph, and one'
    " highlight button for every paragraph you present as an answer, its args carrying that"
    ' paragraph\'s chapter id and paragraph id, and "sentence_indices" holding exactly the positions'
    ' that answer put in "matched_sentence_indexes" (first sentence of the paragraph is 0), the same'
    " count in the same order; an empty list shows the whole paragraph, which is what the tool"
    " marked none for. Pass the sentence positions, never their ids. Chapter and paragraph ids are"
    " required."
    " A find_paragraphs result is a candidate list, not an answer: it matches the words and names"
    " you searched for, not the meaning of the question. Read each returned paragraph's sentences"
    " and decide whether it actually states what the user asked. Include a paragraph only when it"
    " answers; when one is related but does not answer, say so plainly (this paragraph is related"
    " but does not answer the question) rather than presenting it as the answer. If none answer,"
    " say that plainly."
    " When the question asks for the first or earliest occurrence of something, the candidate list is"
    " in reading order: lower chapter_index is an earlier chapter, and within a chapter lower index"
    " (the paragraph's position in that chapter) is an earlier paragraph. Consider the candidates in"
    " that order, skip any that do not actually answer, and present only the earliest paragraph that"
    " does. Search manuscript chapters only for such a question, leaving include_characters false."
    " Do not call get_chapter to read a whole chapter when verifying find_paragraphs candidates:"
    " each candidate already carries its sentences. When a candidate's surrounding paragraphs are"
    " needed to tell who is speaking or acting, pass start_index and end_index to get_chapter"
    " for a small window around that paragraph's index instead of reading the whole chapter."
    ' Each "text" item is a neutral, factual description of what one included paragraph says on its'
    " own. Do not phrase it as an answer to the question, assume the question's premise, or add"
    " events, causes, knowledge, or feelings the paragraph does not state. Attribute a fact to a"
    " person only when the paragraph does. Keep the description independent of the question: a"
    " reader must not be able to infer what was asked from it."
)
_RESPONSE_SCHEMA_NAME = "response_syntax"
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["response"],
    "properties": {
        "response": {
            "type": "array",
            "items": {
                "anyOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["text"],
                        "properties": {"text": {"type": "string"}},
                    },
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["button"],
                        "properties": {
                            "button": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["label", "function", "args"],
                                "properties": {
                                    "label": {"type": "string"},
                                    "function": {"type": "string", "enum": ["highlight"]},
                                    "args": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["chapter_id", "paragraph_id", "sentence_indices"],
                                        "properties": {
                                            "chapter_id": {"type": "string"},
                                            "paragraph_id": {"type": "string"},
                                            "sentence_indices": {
                                                "type": "array",
                                                "items": {"type": "integer"},
                                            },
                                        },
                                    },
                                },
                            }
                        },
                    },
                ]
            },
        }
    },
}


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

    def complete(self, prompt: str, account_id: str = "", document_id: str | None = None) -> str:
        """Send *prompt* to the model and return its reply text.

        *account_id* scopes the per-prompt MCP bearer token minted for the
        call; without a public MCP URL the prompt is sent without MCP.
        *document_id* names the manuscript the user has open, so the model is
        told which document its tool calls should read.
        """
        token: str | None = None
        server_url: str | None = None
        issuer = self._token_issuer() if self._token_issuer is not None else None
        public_url = os.environ.get(_PUBLIC_URL_ENV_VAR)
        if issuer is not None and public_url and public_url.strip():
            token = issuer.mint(uuid.uuid4().hex, account_id)
            server_url = f"{public_url.rstrip('/')}/mcp"
        return str(self._complete(prompt, token, server_url, document_id))

    def _default_complete(
        self,
        prompt: str,
        token: str | None,
        server_url: str | None,
        document_id: str | None = None,
    ) -> str:
        """One responses call with the configured model; MCP tool when it runs."""
        key = os.environ.get(_KEY_ENV_VAR)
        if not key or not key.strip():
            raise MissingApiKeyError("OPENAI_API_KEY is not set")
        payload: dict[str, Any] = {"model": os.environ.get(_MODEL_ENV_VAR, _DEFAULT_MODEL)}
        if server_url and token:
            instructions = _INSTRUCTIONS.format(label=_MCP_SERVER_LABEL, server_url=server_url)
            instructions += _RESPONSE_SYNTAX_INSTRUCTIONS
            if document_id:
                instructions += _DOCUMENT_INSTRUCTIONS.format(document_id=document_id)
            payload["instructions"] = instructions
            payload["tools"] = [
                {
                    "type": "mcp",
                    "server_label": _MCP_SERVER_LABEL,
                    "server_url": server_url,
                    "authorization": token,
                    "require_approval": "never",
                }
            ]
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": _RESPONSE_SCHEMA_NAME,
                    "strict": True,
                    "schema": _RESPONSE_SCHEMA,
                }
            }
        payload["input"] = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
        response = httpx2.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=120.0,
        )
        _raise_for_status(response)
        reply = _reply_from(response.json())
        logger.info("AI reply: %s", reply)
        return reply


def _raise_for_status(response: Any) -> None:
    """Raise on an HTTP error, logging and surfacing the provider's error detail."""
    try:
        response.raise_for_status()
    except Exception as exc:
        detail = _error_detail(response)
        if detail:
            logger.warning("OpenAI responses call failed: %s", detail)
            raise RuntimeError(f"{exc} — {detail}") from exc
        raise


def _error_detail(response: Any) -> str:
    """Extract the provider's error message from a failed HTTP response."""
    try:
        payload = response.json()
    except Exception:  # pylint: disable=broad-exception-caught
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        message = str(error.get("message") or "").strip()
        code = str(error.get("code") or "").strip()
        if code and message:
            return f"{code}: {message}"
        if message:
            return message
    return str(getattr(response, "text", "") or "").strip()


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
