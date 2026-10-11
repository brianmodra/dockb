"""Tests for the two-listener runner: config, app building, and one-loop serving.

``mcp_server`` is specified by ``README_mcp_auth.md`` §1, §5, §8.4 and §8.5: a
shared runner that wires once and serves the manuscript API on the loopback
listener and the bearer-gated MCP endpoint on the public listener, both bound
to ``127.0.0.1``, on one process and one event loop.
"""

# pylint: disable=too-few-public-methods

from __future__ import annotations

import asyncio
import socket
import time

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from dockb.composition import set_mcp_issuer
from dockb.infrastructure.mcp.app import create_mcp_app
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer
from dockb.mcp_server import build_mcp_app, mcp_allowed_hosts, mcp_port, servers


class TestMcpPort:
    """mcp_port() reads DOCKB_MCP_PORT, falling back to 8001."""

    def test_defaults_to_8001(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOCKB_MCP_PORT", raising=False)
        assert mcp_port() == 8001

    def test_reads_dockb_mcp_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCKB_MCP_PORT", "9443")
        assert mcp_port() == 9443

    @pytest.mark.parametrize("bad", ["eight", "70000", "-1", "0", ""])
    def test_rejects_a_non_port(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        monkeypatch.setenv("DOCKB_MCP_PORT", bad)
        with pytest.raises(ValueError):
            mcp_port()


class TestMcpAllowedHosts:
    """mcp_allowed_hosts() honours the override, defaulting to public URL + localhost."""

    def test_defaults_use_public_url_host_and_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOCKB_MCP_ALLOWED_HOSTS", raising=False)
        monkeypatch.setenv("DOCKB_MCP_PUBLIC_URL", "https://mcp.example.com")
        assert mcp_allowed_hosts() == [
            "mcp.example.com",
            "mcp.example.com:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ]

    def test_default_without_public_url_is_localhost_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOCKB_MCP_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv("DOCKB_MCP_PUBLIC_URL", raising=False)
        assert mcp_allowed_hosts() == ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]

    def test_an_unparseable_public_url_falls_back_to_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOCKB_MCP_ALLOWED_HOSTS", raising=False)
        monkeypatch.setenv("DOCKB_MCP_PUBLIC_URL", "not a url")
        assert mcp_allowed_hosts() == ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]

    def test_override_splits_and_trims_commas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOCKB_MCP_ALLOWED_HOSTS", "mcp.a.com, mcp.b.com")
        assert mcp_allowed_hosts() == ["mcp.a.com", "mcp.b.com"]


class TestBuildMcpApp:
    """build_mcp_app() turns the wired issuer and allowlist into the public app."""

    @pytest.mark.asyncio
    async def test_requires_a_wired_issuer(self) -> None:
        set_mcp_issuer(None)
        with pytest.raises(RuntimeError):
            build_mcp_app()

    @pytest.mark.asyncio
    async def test_serves_only_the_gated_mcp_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DOCKB_MCP_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv("DOCKB_MCP_PUBLIC_URL", raising=False)
        issuer = PromptTokenIssuer(ttl_seconds=60)
        set_mcp_issuer(issuer)
        try:
            app = build_mcp_app()
            async with app.router.lifespan_context(app):
                async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1:8001") as client:
                    assert (await client.get("/mcp")).status_code == 401
                    assert (await client.get("/api/documents")).status_code == 401

                token = issuer.mint("prompt-serve")
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8001",
                    headers={"Authorization": f"Bearer {token}"},
                ) as http_client:
                    async with streamable_http_client("http://127.0.0.1:8001/mcp", http_client=http_client) as streams:
                        async with ClientSession(streams[0], streams[1]) as session:
                            await session.initialize()
                            assert (await session.list_tools()).tools == []
        finally:
            set_mcp_issuer(None)


class TestServers:
    """servers() builds two uvicorn servers that serve concurrently on one loop."""

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    async def _reachable(url: str, *, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                async with httpx2.AsyncClient(timeout=1.0) as client:
                    response = await client.get(url)
            except httpx2.ConnectError:
                await asyncio.sleep(0.05)
                continue
            assert response.status_code != 404
            return
        pytest.fail(f"server never became reachable at {url}")

    @pytest.mark.asyncio
    async def test_both_listeners_answer_in_the_same_process(self) -> None:
        issuer = PromptTokenIssuer(ttl_seconds=60)
        mcp_app = create_mcp_app(
            issuer,
            allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*"],
        )
        loopback_app = Starlette(routes=[Route("/api/health", lambda _request: JSONResponse({"ok": True}))])

        loopback_port = self._free_port()
        public_port = self._free_port()
        loopback, public = servers(
            loopback_app,
            mcp_app,
            loopback_port=loopback_port,
            public_port=public_port,
        )

        loopback_task = asyncio.create_task(loopback.serve())
        public_task = asyncio.create_task(public.serve())
        try:
            await self._reachable(f"http://127.0.0.1:{loopback_port}/api/health")
            await self._reachable(f"http://127.0.0.1:{public_port}/mcp")

            async with httpx2.AsyncClient() as client:
                assert (await client.get(f"http://127.0.0.1:{loopback_port}/api/health")).status_code == 200
                assert (await client.get(f"http://127.0.0.1:{public_port}/mcp")).status_code == 401

            token = issuer.mint("prompt-serve")
            async with httpx2.AsyncClient(
                base_url=f"http://127.0.0.1:{public_port}",
                headers={"Authorization": f"Bearer {token}"},
            ) as http_client:
                async with streamable_http_client(f"http://127.0.0.1:{public_port}/mcp", http_client=http_client) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()
                        assert (await session.list_tools()).tools == []
        finally:
            loopback.should_exit = True
            public.should_exit = True
            await asyncio.gather(loopback_task, public_task, return_exceptions=True)
