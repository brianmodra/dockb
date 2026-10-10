"""Tests for the public MCP application and its bearer-token gate.

The application under test is ``create_mcp_app``: an MCP server with no tools,
mounted so ``/mcp`` is its only route, with ``BearerAuthMiddleware`` in front
and a lifespan that starts the MCP session manager. ``README_mcp_auth.md`` §2
and §5 are the specification.
"""

from __future__ import annotations

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dockb.infrastructure.mcp.app import create_mcp_app
from dockb.infrastructure.mcp.auth import BearerAuthMiddleware, get_prompt_id
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

_OTHER_ISSUER = PromptTokenIssuer(ttl_seconds=60)


def _issuer() -> PromptTokenIssuer:
    return PromptTokenIssuer(ttl_seconds=60)


def _client(issuer: PromptTokenIssuer) -> TestClient:
    return TestClient(
        create_mcp_app(
            issuer,
            allowed_hosts=["testserver", "testserver:*", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"],
        )
    )


# --- the bearer gate, checked without running a server at all ---


def _auth_host(issuer: PromptTokenIssuer) -> Starlette:
    """A host app running only the middleware, so the gate is testable in isolation."""

    def echo(_request) -> JSONResponse:
        return JSONResponse({"prompt_id": get_prompt_id()})

    inner = Starlette(routes=[Route("/", echo)])
    return Starlette(
        routes=inner.routes,
        middleware=[Middleware(BearerAuthMiddleware, issuer=issuer)],
    )


def test_missing_authorization_header_is_401() -> None:
    issuer = _issuer()
    with TestClient(_auth_host(issuer)) as client:
        response = client.get("/")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"error": "invalid_token"}


def test_non_bearer_scheme_is_401() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-1")
    with TestClient(_auth_host(issuer)) as client:
        response = client.get("/", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


def test_empty_token_is_401() -> None:
    issuer = _issuer()
    with TestClient(_auth_host(issuer)) as client:
        response = client.get("/", headers={"Authorization": "Bearer "})
    assert response.status_code == 401


def test_valid_token_passes_and_binds_the_prompt_id() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-7")
    with TestClient(_auth_host(issuer)) as client:
        response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"prompt_id": "prompt-7"}


def test_token_from_another_issuer_is_401() -> None:
    foreign = _OTHER_ISSUER.mint("prompt-8")
    with TestClient(_auth_host(_issuer())) as client:
        response = client.get("/", headers={"Authorization": f"Bearer {foreign}"})
    assert response.status_code == 401


def test_expired_token_is_401() -> None:
    issuer = PromptTokenIssuer(ttl_seconds=-1)
    token = issuer.mint("prompt-9")
    with TestClient(_auth_host(issuer)) as client:
        response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_get_prompt_id_is_none_outside_a_request() -> None:
    assert get_prompt_id() is None


# --- the public application ---


def test_every_route_is_401_without_a_token() -> None:
    with _client(_issuer()) as client:
        assert client.get("/mcp").status_code == 401
        assert client.post("/mcp", json={}).status_code == 401
        assert client.get("/api/documents").status_code == 401


def test_no_manuscript_route_is_served_with_a_valid_token() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-11")
    with _client(issuer) as client:
        response = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.text != ""


def test_no_oauth_discovery_endpoint_is_served() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-13")
    with _client(issuer) as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


def test_a_disallowed_host_is_rejected() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-11")
    app = create_mcp_app(issuer, allowed_hosts=["only.example.com", "only.example.com:*"])
    with TestClient(app, base_url="http://other.example.net") as client:
        response = client.get("/mcp", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 421


@pytest.mark.asyncio
async def test_tools_list_is_empty_with_a_valid_token() -> None:
    issuer = _issuer()
    token = issuer.mint("prompt-12")
    app = create_mcp_app(
        issuer,
        allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "testserver", "testserver:*"],
    )

    async with app.router.lifespan_context(app):
        http_client = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1:8001",
            headers={"Authorization": f"Bearer {token}"},
        )
        async with streamable_http_client("http://127.0.0.1:8001/mcp", http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                assert (await session.list_tools()).tools == []
