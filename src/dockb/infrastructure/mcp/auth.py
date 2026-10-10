"""Bearer-token verification middleware for the public MCP listener.

A pure-ASGI middleware in front of the MCP endpoint: it reads
``Authorization: Bearer <token>``, verifies the token with the prompt-token
issuer, and either lets the request through with the prompt identity bound to
it, or answers ``401`` with a bare ``WWW-Authenticate: Bearer`` before anything
is parsed. See this package's ``README.md`` and ``README_mcp_auth.md`` §2 and §5.
"""

from __future__ import annotations

from contextvars import ContextVar

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

_prompt_id: ContextVar[str | None] = ContextVar("mcp_prompt_id", default=None)


def get_prompt_id() -> str | None:
    """Return the prompt identity bound to the current request, or None."""
    return _prompt_id.get()


class BearerAuthMiddleware:  # pylint: disable=too-few-public-methods
    """Verify ``Authorization: Bearer <token>`` before the application runs.

    Non-HTTP scopes (the lifespan) pass through untouched, and the check is pure
    ASGI rather than ``BaseHTTPMiddleware`` so the transport's streaming
    responses are not buffered or disturbed.
    """

    def __init__(self, app: ASGIApp, issuer: PromptTokenIssuer) -> None:
        self.app = app
        self._issuer = issuer

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scheme, _, token = Headers(scope=scope).get("authorization", "").partition(" ")
        prompt_id = self._issuer.verify(token) if scheme.lower() == "bearer" and token else None
        if prompt_id is None:
            response = JSONResponse(
                {"error": "invalid_token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        _prompt_id.set(prompt_id)
        await self.app(scope, receive, send)
