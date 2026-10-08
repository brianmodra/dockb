# MCP Token Infrastructure

## Executive Summary

This package holds the mint-and-verify pair for the per-prompt bearer token that
authenticates OpenAI's infrastructure when it calls the MCP server. There is no
credential store, no signing key and no admin CLI: each prompt's secret is born
in memory, sits in a map keyed by the token's expiry, and dies with its entry,
so a leaked token is useless once that window passes and nothing secret is left
on disk.

`PromptTokenIssuer` is the whole of it — `mint` makes a token for one prompt and
`verify` says which prompt a presented token belongs to, or rejects it. Read
this for what the token looks like and what makes one valid; the threat model,
the two-listener split and why this is a MAC rather than a signature are in
`README_mcp_auth.md` at the repository root.

## Package Structure

```
infrastructure/mcp/
├── README.md           # This file
├── __init__.py         # Re-exports PromptTokenIssuer
└── prompt_tokens.py    # PromptTokenIssuer — mint() and verify()
```

## Components

### `PromptTokenIssuer`

- `mint(prompt_id: str) -> str` — generates a fresh secret, prunes entries whose
  expiry has passed, inserts the new secret under *now* + the TTL, and returns
  the token `expiry.prompt_id.mac(expiry + "." + prompt_id)`. The MAC is
  HMAC-SHA256 under the entry's secret; `prompt_id` is supplied by the caller
  (the MCP endpoint's handle for one prompt) and is not secret.
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

What this deliberately does **not** have: a table of issued tokens, a keypair, a
revocation command, or a credential that outlives the process. Revocation is the
TTL and the restart (`README_mcp_auth.md` §7).
