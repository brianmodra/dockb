"""Config and runner for the two-listener DockB server.

One process, one event loop, two listeners (``README_mcp_auth.md`` §1 and §5):
the loopback listener serves the manuscript API on ``127.0.0.1:8000`` and the
public listener serves the bearer-gated MCP endpoint on ``127.0.0.1:8001``
(configurable via ``DOCKB_MCP_PORT``), reached only through the tunnel.

``serve()`` wires the services once, builds both applications, and runs the two
uvicorn servers side by side on the current loop, unwiring and closing the
Neo4j pool afterwards. ``main.py`` calls it from ``__main__``.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from starlette.types import ASGIApp

from dockb.app_factory import create_app
from dockb.composition import (
    get_mcp_issuer,
    resolve_document_base_dir,
    unwire,
    wire,
)
from dockb.infrastructure.mcp.app import create_mcp_app
from dockb.infrastructure.neo4j.session_factory import SessionFactory

LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 8000
PUBLIC_HOST = "127.0.0.1"

_MCP_PORT_ENV_VAR = "DOCKB_MCP_PORT"
_DEFAULT_MCP_PORT = 8001
_MCP_ALLOWED_HOSTS_ENV_VAR = "DOCKB_MCP_ALLOWED_HOSTS"
_PUBLIC_URL_ENV_VAR = "DOCKB_MCP_PUBLIC_URL"


def mcp_port() -> int:
    """Return the public listener's port, ``DOCKB_MCP_PORT`` or 8001."""
    raw = os.environ.get(_MCP_PORT_ENV_VAR, str(_DEFAULT_MCP_PORT))
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"{_MCP_PORT_ENV_VAR} must be an integer, got {raw!r}") from None
    if not 0 < port <= 65535:
        raise ValueError(f"{_MCP_PORT_ENV_VAR} must be a port between 1 and 65535, got {port}")
    return port


def mcp_allowed_hosts() -> list[str]:
    """Return the transport's host allowlist (env override or defaults)."""
    configured = os.environ.get(_MCP_ALLOWED_HOSTS_ENV_VAR)
    if configured and configured.strip():
        return [host.strip() for host in configured.split(",") if host.strip()]
    return default_allowed_hosts()


def default_allowed_hosts() -> list[str]:
    """Return the allowlist when ``DOCKB_MCP_ALLOWED_HOSTS`` is unset.

    The public URL's host and ``localhost`` are each accepted with and without a
    ``:*`` port wildcard, because the transport matches the ``Host`` header
    exactly unless every port is allowed for that host (``README_mcp_auth.md``
    §8.5). An absent or unparseable ``DOCKB_MCP_PUBLIC_URL`` leaves the
    localhost forms only.
    """
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    public_url = os.environ.get(_PUBLIC_URL_ENV_VAR)
    if public_url:
        host = urlparse(public_url).hostname
        if host:
            hosts = [host, f"{host}:*", *hosts]
    return hosts


def build_mcp_app() -> ASGIApp:
    """Build the public MCP application from the wired issuer and allowlist."""
    return create_mcp_app(get_mcp_issuer(), allowed_hosts=mcp_allowed_hosts())


def servers(
    loopback_app: ASGIApp,
    mcp_app: ASGIApp,
    *,
    loopback_port: int = LOOPBACK_PORT,
    public_port: int | None = None,
) -> tuple[uvicorn.Server, uvicorn.Server]:
    """Return the two uvicorn servers that make up the running process."""
    if public_port is None:
        public_port = mcp_port()
    return (
        uvicorn.Server(uvicorn.Config(loopback_app, host=LOOPBACK_HOST, port=loopback_port)),
        uvicorn.Server(uvicorn.Config(mcp_app, host=PUBLIC_HOST, port=public_port)),
    )


async def serve(loopback_app: ASGIApp | None = None) -> None:
    """Wire once and run both listeners on the current event loop.

    Wires before building the MCP application so the shared issuer exists, then
    runs the loopback and public servers side by side and unwires in ``finally``
    so the Neo4j pool is closed on shutdown. *loopback_app* overrides the
    manuscript API application (used by tests); when omitted it is built here.
    """
    load_dotenv()
    os.chdir(Path(__file__).resolve().parents[2] / "run")
    session_factory = SessionFactory(
        uri=os.environ["NEO4J_URL"],
        user=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
    )
    document_base_dir = resolve_document_base_dir()
    wire(
        session_factory,
        document_base_dir=document_base_dir,
        accounts_base_dir=document_base_dir.parent,
    )
    try:
        application = loopback_app if loopback_app is not None else create_app()
        loopback, public = servers(application, build_mcp_app())
        running = [asyncio.create_task(loopback.serve()), asyncio.create_task(public.serve())]
        try:
            await asyncio.gather(*running)
        finally:
            # If either listener fails (e.g. its port is taken), stop the other
            # before unwiring, so its still-served requests cannot hit a closed
            # SessionFactory.
            loopback.should_exit = True
            public.should_exit = True
            await asyncio.gather(*running, return_exceptions=True)
    finally:
        unwire()
        session_factory.close()
