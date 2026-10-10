"""The public MCP application — one route, bearer-gated, no tools.

``create_mcp_app`` builds the application the public listener serves: an MCP
server with no tools mounted so its endpoint is the only route, at ``/mcp``,
with bearer verification in front of it and a lifespan that starts the MCP
session manager. It mounts no manuscript router and serves no editor shell.
See this package's ``README.md`` and ``README_mcp_auth.md`` §5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

from dockb.infrastructure.mcp.auth import BearerAuthMiddleware
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer


def create_mcp_app(issuer: PromptTokenIssuer, *, allowed_hosts: Sequence[str]) -> Starlette:
    """Return the ASGI application the public listener serves.

    *issuer* verifies the per-prompt bearer token on every request;
    *allowed_hosts* is the list of ``Host`` values the MCP transport will
    answer (see ``README_mcp_auth.md`` §8.5).
    """
    mcp = MCPServer("DockB")
    security = TransportSecuritySettings(allowed_hosts=list(allowed_hosts))
    mcp_app = mcp.streamable_http_app(transport_security=security)

    @asynccontextmanager
    async def lifespan(_application: Starlette) -> AsyncIterator[None]:
        # Mounting a sub-application disables its built-in lifespan, so the
        # session manager is started here, for the lifetime of this host app.
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[Mount("/", app=mcp_app)],
        middleware=[Middleware(BearerAuthMiddleware, issuer=issuer)],
        lifespan=lifespan,
    )
