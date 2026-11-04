"""The operator's MCP token mint route — POST /api/mcp/mint.

The MCP tools read one account's books, and the bearer token they accept is
minted by the live in-memory issuer inside this very process — so the operator
needs a way to ask this process for one. The route is that ask: it is gated by
the server's own secret (``DOCKB_SECRET_KEY``) rather than by a session,
because accounts carry no admin flag and the mint is an operator power, like
the accounts CLI. The route lives on the loopback listener only.
"""

# pylint: disable=invalid-name,missing-function-docstring,global-statement

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from dockb.controllers.auth import get_auth_service
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

_issuer: PromptTokenIssuer | None = None
_mint_secret: str | None = None


def set_mint_issuer(issuer: PromptTokenIssuer | None) -> None:
    """Set (or clear) the live issuer tokens are minted from."""
    global _issuer  # noqa: PLW0603
    _issuer = issuer


def set_mint_secret(secret: str | None) -> None:
    """Set (or clear) the operator secret the route demands."""
    global _mint_secret  # noqa: PLW0603
    _mint_secret = secret


class MintRequest(BaseModel):
    """The prompt to mint for, and the account it should read as."""

    prompt_id: str
    account_id: str

    @field_validator("prompt_id", "account_id")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class MintResponse(BaseModel):
    """The minted bearer token, and what it is bound to."""

    token: str
    prompt_id: str
    account_id: str
    ttl_seconds: float


@router.post("/mint")
def mint(
    request: MintRequest,
    x_mcp_mint_secret: str | None = Header(default=None),
    auth: Any = Depends(get_auth_service),
) -> dict[str, Any]:
    presented = x_mcp_mint_secret or ""
    if not _mint_secret or not presented or not hmac.compare_digest(presented, _mint_secret):
        raise HTTPException(status_code=403, detail="mint_secret_rejected")
    if _issuer is None:
        raise HTTPException(status_code=503, detail="mcp_issuer_unavailable")
    if auth is None or auth.get_user(request.account_id) is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    token = _issuer.mint(request.prompt_id, request.account_id)
    return MintResponse(
        token=token,
        prompt_id=request.prompt_id,
        account_id=request.account_id,
        ttl_seconds=_issuer.ttl_seconds,
    ).model_dump()
