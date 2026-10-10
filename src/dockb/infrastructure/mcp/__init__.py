"""MCP per-prompt token infrastructure.

Mints and verifies the bearer token OpenAI's infrastructure presents on MCP
requests, and builds the public application that enforces it. No credential
store, no signing key, no admin CLI: the secret for a prompt lives in a
module-level map keyed by expiry and dies with its entry. See
``README_mcp_auth.md`` §3 and this package's ``README.md``.
"""

from __future__ import annotations

from dockb.infrastructure.mcp.app import create_mcp_app
from dockb.infrastructure.mcp.auth import BearerAuthMiddleware, get_prompt_id
from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

__all__ = ["BearerAuthMiddleware", "PromptTokenIssuer", "create_mcp_app", "get_prompt_id"]
