# MCP Token Infrastructure

## Executive Summary

This package authenticates OpenAI's infrastructure against DockB's MCP server with a
per-prompt bearer token that exists only in memory: each prompt's secret is born when
the editor sends a chat prompt, is bound to the signed-in account, and dies when its
expiry passes or the process restarts. There is no credential store, no signing key
and no admin CLI, so a leaked token is useless once its window passes and nothing
secret is left on disk.

The package also carries the two manuscript tools the token unlocks (`tools.py`): one
returns a chapter's paragraphs; the other searches paragraphs by a criteria tree —
word, text, and character leaves over and/or group nodes — that compiles into a single
Cypher query answered entirely in the database, refusing an unknown or other-account
document instead of answering empty. Read this for what the token looks like, what
makes one valid, the account it is bound to, and how the tools read one account's
books; the threat model, the two-listener split and why this is a MAC rather than a
signature are in `README_mcp_auth.md` at the repository root.

## Package Structure

```
infrastructure/mcp/
├── README.md           # This file
├── __init__.py         # Re-exports the token pair, the middleware and the app
├── prompt_tokens.py    # PromptTokenIssuer — mint() and verify()
├── auth.py             # BearerAuthMiddleware — the Authorization check
├── tools.py            # mount_tools() — the manuscript tools

└── app.py              # create_mcp_app() — the MCP-only public ASGI app
```

The runner that puts this package on a port lives one level up, at
`src/dockb/mcp_server.py`: `composition.wire()` builds a single
`PromptTokenIssuer` and installs it as the shared DI global, `build_mcp_app()`
reads it back to build the public application, and `serve()` runs the loopback
and public listeners on one event loop.

## Components

### `PromptTokenIssuer`

- `mint(prompt_id: str, account_id: str) -> str` — generates a fresh secret,
  prunes entries whose expiry has passed, inserts the new secret **with the
  account it is bound to** under *now* + the TTL, and returns the token
  `expiry.prompt_id.mac(expiry + "." + prompt_id)`. The MAC is HMAC-SHA256
  under the entry's secret; `prompt_id` is supplied by the caller (the MCP
  endpoint's handle for one prompt) and is not secret. The account is the
  subject the tools read as — minting without one is refused.
- `verify(token: str) -> str | None` — parses the expiry and prompt identity,
  rejects a token whose expiry has passed or whose entry is not live, recomputes
  the MAC with that entry's secret and compares in constant time. Every attempt
  is logged with its prompt identity and the outcome, so a token seen out of
  place traces to one request. The identity logged is sanitised — control
  characters are collapsed — because it is parsed from the presented token.
  Returns the prompt identity when valid, `None` otherwise.
- `ttl_seconds` — from `DOCKB_MCP_TOKEN_TTL_SECONDS`, default 300; read from the
  environment in the constructor.

Entries are keyed by the expiry exactly as it appears in the token — an integer
count of microseconds, so the field is dot-free and two mints cannot share a
key — and an entry is a `prompt_id → secret` mapping so two prompts whose expiry
collides to the same string still do not invalidate each other. Expiry and MAC
travel in the clear; neither is a secret, and the MAC covers both, so neither
can be altered without invalidating the token.

### `BearerAuthMiddleware`

A pure-ASGI middleware placed in front of the MCP endpoint. For an HTTP request
it reads `Authorization: Bearer <token>`, calls the issuer's `verify`, and either
records the prompt identity on the request and passes it through, or answers
`401` with a bare `WWW-Authenticate: Bearer` and a JSON error — before anything
is parsed, so an unauthenticated request never reaches a handler. Non-HTTP scopes
(the lifespan) pass through untouched. It is plain ASGI rather than
`BaseHTTPMiddleware` so it does not disturb the transport's streaming responses.

### `create_mcp_app`

`create_mcp_app(issuer, *, allowed_hosts, chapter_repo, document_repo, search_repo,
mentions_repo)` returns the application the public listener serves: an MCP server
carrying **only the manuscript tools**, mounted so its endpoint is the
one route at `/mcp`, with the middleware above in front of it and a lifespan that
starts the MCP session manager. It mounts no manuscript router and serves no
editor shell, so nothing the tunnel forwards can reach the manuscript API. The
host allowlist it is given is the list of `Host` values the transport will
answer; a request to any other host is refused before any handler runs
(`README_mcp_auth.md` §5, §8.5).

What this deliberately does **not** have: a table of issued tokens, a keypair, a
revocation command, or a credential that outlives the process. Revocation is the
TTL and the restart (`README_mcp_auth.md` §7).
