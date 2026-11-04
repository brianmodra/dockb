"""The operator's MCP mint route: POST /api/mcp/mint."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dockb.controllers import mcp_mint
from dockb.controllers.auth import set_auth_service
from dockb.controllers.mcp_mint import router as mint_router
from dockb.controllers.mcp_mint import set_mint_issuer
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

_SECRET = "operator-secret"


@pytest.fixture()
def app():
    application = FastAPI()
    application.include_router(mint_router)
    issuer = PromptTokenIssuer(ttl_seconds=60)
    set_mint_issuer(issuer)
    mcp_mint.set_mint_secret(_SECRET)
    auth = MagicMock()
    auth.get_user_by_id.side_effect = lambda user_id: {"id": user_id, "username": "abby"} if user_id == "acct-1" else None
    set_auth_service(auth)
    return application


def _client(app) -> TestClient:
    return TestClient(app)


def _headers(secret: str = _SECRET) -> dict[str, str]:
    return {"X-MCP-Mint-Secret": secret}


def test_mints_a_live_token_bound_to_the_account(app) -> None:
    response = _client(app).post("/api/mcp/mint", json={"prompt_id": "prompt-9", "account_id": "acct-1"}, headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["prompt_id"] == "prompt-9"
    assert body["account_id"] == "acct-1"
    assert body["ttl_seconds"] == 60
    issuer = mcp_mint._issuer  # pylint: disable=protected-access
    assert issuer.verify(body["token"]) == "prompt-9"
    assert issuer.account_of(body["token"]) == "acct-1"


def test_a_wrong_or_missing_secret_is_refused(app) -> None:
    client = _client(app)

    assert client.post("/api/mcp/mint", json={"prompt_id": "p", "account_id": "acct-1"}).status_code == 403
    assert (
        client.post("/api/mcp/mint", json={"prompt_id": "p", "account_id": "acct-1"}, headers={"X-MCP-Mint-Secret": "nope"}).status_code
        == 403
    )


def test_an_unknown_account_is_refused(app) -> None:
    response = _client(app).post("/api/mcp/mint", json={"prompt_id": "prompt-9", "account_id": "acct-ghost"}, headers=_headers())

    assert response.status_code == 404


def test_a_blank_prompt_id_or_account_is_rejected(app) -> None:
    client = _client(app)

    assert client.post("/api/mcp/mint", json={"prompt_id": "  ", "account_id": "acct-1"}, headers=_headers()).status_code == 422
    assert client.post("/api/mcp/mint", json={"prompt_id": "p", "account_id": " "}, headers=_headers()).status_code == 422


def teardown_function() -> None:
    set_mint_issuer(None)
    mcp_mint.set_mint_secret(None)
    set_auth_service(None)
