"""MCP per-prompt token infrastructure.

Mints and verifies the bearer token OpenAI's infrastructure presents on MCP
requests. No credential store, no signing key, no admin CLI: the secret for a
prompt lives in a module-level map keyed by expiry and dies with its entry.
See ``README_mcp_auth.md`` §3 and this package's ``README.md``.
"""

from __future__ import annotations

from dockb.infrastructure.mcp.prompt_tokens import PromptTokenIssuer

__all__ = ["PromptTokenIssuer"]
