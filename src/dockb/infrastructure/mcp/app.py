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
from dockb.infrastructure.mcp.tools import mount_tools
from dockb.repositories.chapter_repository import ChapterRepository
from dockb.repositories.paragraph_search_repository import ParagraphSearchRepository


def create_mcp_app(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    issuer: PromptTokenIssuer,
    *,
    allowed_hosts: Sequence[str],
    chapter_repo: ChapterRepository,
    search_repo: ParagraphSearchRepository,
) -> Starlette:
    """Return the ASGI application the public listener serves.

    *issuer* verifies the per-prompt bearer token on every request;
    *allowed_hosts* is the list of ``Host`` values the MCP transport will
    answer (see ``README_mcp_auth.md`` §8.5); the repositories are what the
    manuscript tools read through, owner-scoped to the token's account.
    """
    mcp = MCPServer("DockB")
    mount_tools(
        mcp,
        chapter_repo=chapter_repo,
        search_repo=search_repo,
    )
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
